"""AD (Altium Designer) 库导出。

将立创官方器件数据（标准版接口 result JSON）转换为 AD 原生二进制库：
  · {编号}_{符号名}.SchLib   —— 原理图符号库
  · {编号}_{封装名}.PcbLib   —— PCB 封装库（可选内嵌 3D STEP 模型）

转换由内置的精简版 LCSC3D 转换链完成（AGPL-3.0）。
版权与出处详见 lcsc3d/NOTICE.txt 与 lcsc3d/LICENSE。
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import replace

# 3D 模型资源端点（国内镜像优先，国际站兜底），{uuid} 为封装 SVGNODE 中的资源编号
MODEL_STEP_URLS = (
    'https://modules.lceda.cn/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}',
    'https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}',
)
MODEL_OBJ_URLS = (
    'https://modules.lceda.cn/3dmodel/{uuid}',
    'https://modules.easyeda.com/3dmodel/{uuid}',
)


class AdExportError(Exception):
    """AD 库导出失败（含可读原因）。"""


def _safe_filename(name, fallback):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', str(name or '').strip())
    name = name.strip('. ')
    return name[:120] or fallback


def _domain_errors(component, domains):
    result = []
    for d in getattr(component, 'diagnostics', ()) or ():
        try:
            if d.severity == 'error' and d.domain in domains:
                result.append(str(d.message))
        except AttributeError:
            continue
    return result


def find_model_uuid(component_data):
    """从封装数据中提取 3D 模型资源编号（SVGNODE 记录）。无模型返回 None。"""
    try:
        package = component_data.get('packageDetail') if isinstance(component_data, dict) else None
        doc = package.get('dataStr') if isinstance(package, dict) else None
        if isinstance(doc, str):
            doc = json.loads(doc)
        for shape in (doc or {}).get('shape') or []:
            if not (isinstance(shape, str) and shape.startswith('SVGNODE~')):
                continue
            node = json.loads(shape.partition('~')[2])
            attrs = node.get('attrs') or {}
            if attrs.get('c_etype') not in (None, 'outline3D'):
                continue
            uuid = attrs.get('uuid')
            if isinstance(uuid, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', uuid):
                return uuid
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def _try_fetch(urls, fetch, validate=None):
    """按顺序尝试多个镜像地址；全部失败时返回 None（不抛异常）。"""
    for url in urls:
        try:
            data = fetch(url)
        except Exception:  # noqa: BLE001 - 逐个镜像兜底
            continue
        if not data:
            continue
        if validate is not None and not validate(data):
            continue
        return data
    return None


def _valid_step(data):
    return (isinstance(data, bytes) and bool(data) and len(data) <= 64 * 1024 * 1024
            and b'ISO-10303-21;' in data[:2048] and b'END-ISO-10303-21;' in data[-2048:])


class _ModelStep:
    """resolve_models 期望的 STEP 载荷（与 LCSC3D 服务层 StepPayload 同构）。"""
    __slots__ = ('data', 'used_library', 'identifier')

    def __init__(self, data, identifier):
        self.data = data
        self.used_library = False
        self.identifier = identifier


def export_altium(component_data, part, out_dir, check_cancelled=None, skip_existing=False,
                  *, embed_model=False, model_layer=1, fetch=None, log=None):
    """将单个立创器件的官方数据导出为 AD 库文件。

    component_data: 立创标准版 API 的 result dict（含 dataStr / packageDetail）。
    part:           立创编号，如 C131443。
    out_dir:        输出目录（自动创建）。
    check_cancelled: 可选回调；每阶段调用一次，抛异常即中止。
    skip_existing:  True 且两个库文件均已存在时跳过转换。
    embed_model:    True 时将官方 3D STEP 内嵌进 PcbLib（需提供 fetch）。
    model_layer:    AD 机械层号 1~32（3D 模型放置层，默认 1）。
    fetch:          下载回调 fetch(url) -> bytes；用于获取 STEP/OBJ 模型资源。
    log:            可选日志回调 log(message)。

    返回 dict: {status: 'ok'|'skip', schlib, pcblib, symbol_name, footprint_name,
                schlib_size, pcblib_size, embedded, model_diagnostics, diagnostics}
    """
    if sys.platform != 'win32':
        raise AdExportError('AD 库导出依赖 Windows 组件（ole32）')
    if not isinstance(component_data, dict) or not component_data.get('dataStr'):
        raise AdExportError('缺少器件数据（dataStr）')

    check = check_cancelled or (lambda: None)
    note = log or (lambda message: None)

    from lcsc3d.eda.easyeda_import import parse_component
    from lcsc3d.eda.altium import export_schlib, export_pcblib
    from lcsc3d.core.errors import DownloadError

    try:
        component = parse_component(component_data, part, check)
    except DownloadError as exc:
        raise AdExportError(f'器件数据解析失败：{exc}') from exc

    if component.symbol is None:
        errors = _domain_errors(component, ('symbol',))
        raise AdExportError('该器件无可用符号数据' + (f'（{errors[0]}）' if errors else ''))
    if component.footprint is None:
        errors = _domain_errors(component, ('footprint',))
        raise AdExportError('该器件无可用封装数据' + (f'（{errors[0]}）' if errors else ''))

    symbol_name = _safe_filename(component.symbol.name, part)
    footprint_name = _safe_filename(component.footprint.name, part + '_Footprint')
    schlib_path = os.path.join(out_dir, f'{part}_{symbol_name}.SchLib')
    pcblib_path = os.path.join(out_dir, f'{part}_{footprint_name}.PcbLib')

    if skip_existing and os.path.exists(schlib_path) and os.path.exists(pcblib_path):
        return {'status': 'skip', 'schlib': schlib_path, 'pcblib': pcblib_path,
                'symbol_name': symbol_name, 'footprint_name': footprint_name,
                'schlib_size': os.path.getsize(schlib_path),
                'pcblib_size': os.path.getsize(pcblib_path),
                'embedded': None, 'model_diagnostics': [], 'diagnostics': []}

    embedded = False
    model_diagnostics = []
    model_assets = None

    if embed_model and fetch is not None:
        model_uuid = find_model_uuid(component_data)
        if model_uuid is None:
            note('      · 该器件无关联 3D 模型，PcbLib 不含内嵌模型')
        else:
            note('      · 正在获取 3D 模型资源（STEP+OBJ）...')
            step_bytes = _try_fetch(
                [u.format(uuid=model_uuid) for u in MODEL_STEP_URLS], fetch, _valid_step)
            obj_bytes = _try_fetch(
                [u.format(uuid=model_uuid) for u in MODEL_OBJ_URLS], fetch)
            obj_text = obj_bytes.decode('utf-8-sig', 'ignore') if obj_bytes else None
            if obj_text and ('<html' in obj_text[:300].lower() or '<!doctype' in obj_text[:300].lower()):
                obj_text = None
            if not step_bytes or not obj_text:
                note('      · 3D 模型资源获取失败，PcbLib 不含内嵌模型')
            else:
                try:
                    from lcsc3d.models.model_export import resolve_models
                    from lcsc3d.models.model_geometry import obj_origin

                    def _step_fetch(reference):
                        if reference.uuid != model_uuid:
                            raise DownloadError('未获取该模型文件')
                        return _ModelStep(step_bytes, reference.uuid)

                    def _origin_fetch(reference):
                        if reference.uuid != model_uuid:
                            raise DownloadError('未获取该模型放置基准')
                        return obj_origin(obj_text, check)

                    component, payloads = resolve_models(
                        component, _step_fetch, check,
                        prepare_altium=True, origin_fetch=_origin_fetch)
                    model_assets = payloads
                    embedded = any(m.transform for m in component.models)
                    model_diagnostics = [
                        str(d.message) for d in component.diagnostics
                        if d.domain == 'model3d' and d.severity in ('error', 'warning')]
                    if embedded:
                        note('      · 3D 模型已按官方放置参数就位，嵌入 PcbLib')
                    else:
                        note('      · 3D 模型放置参数不可用，PcbLib 不内嵌模型')
                except Exception as exc:  # noqa: BLE001 - 内嵌失败时降级为普通导出
                    model_diagnostics = [f'{type(exc).__name__}: {exc}']
                    note(f'      · 3D 内嵌准备失败，降级为普通 PcbLib（{exc}）')
                    component = replace(component, models=(), model_assets=())
                    model_assets = None
                    embedded = False

    if not embedded:
        # 不内嵌 3D 模型：剥离模型信息，避免因缺少模型资源而失败。
        component = replace(component, models=(), model_assets=())
        model_assets = None

    check()
    try:
        schlib_bytes = export_schlib(component, part, check)
        check()
        pcblib_bytes = export_pcblib(component, part, check,
                                     model_assets=model_assets, model_layer=model_layer)
    except DownloadError as exc:
        raise AdExportError(f'转换失败：{exc}') from exc
    except AdExportError:
        raise
    except Exception as exc:  # noqa: BLE001 - 保留类型名便于排查
        raise AdExportError(f'转换异常：{type(exc).__name__}: {exc}') from exc

    os.makedirs(out_dir, exist_ok=True)
    with open(schlib_path, 'wb') as f:
        f.write(schlib_bytes)
    with open(pcblib_path, 'wb') as f:
        f.write(pcblib_bytes)

    return {'status': 'ok', 'schlib': schlib_path, 'pcblib': pcblib_path,
            'symbol_name': symbol_name, 'footprint_name': footprint_name,
            'schlib_size': len(schlib_bytes), 'pcblib_size': len(pcblib_bytes),
            'embedded': embedded, 'model_diagnostics': model_diagnostics,
            'diagnostics': _domain_errors(component, ('symbol', 'footprint'))}
