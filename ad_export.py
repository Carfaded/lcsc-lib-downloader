"""AD (Altium Designer) 库导出与合并。

将立创官方器件数据（标准版接口 result JSON）转换为 AD 原生二进制库：
  · 单器件: {编号}_{符号名}.SchLib + {编号}_{封装名}.PcbLib
  · 多器件合并: LCSC3D.SchLib + LCSC3D.PcbLib（封装自动去重、符号引用最终封装名）

可选把官方 3D STEP 模型内嵌进 PcbLib（含内嵌模型时，AD 中按 3 键查看立体效果）。

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


def _parse_component_checked(component_data, part, check):
    """解析器件数据并校验符号/封装齐备。"""
    if not isinstance(component_data, dict) or not component_data.get('dataStr'):
        raise AdExportError('缺少器件数据（dataStr）')
    from lcsc3d.eda.easyeda_import import parse_component
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
    return component


def _resolve_embedding(component, component_data, part, check, *, embed_model, fetch, note):
    """按需获取并解析 3D 模型放置；失败或无模型时剥离模型信息（降级为普通导出）。

    返回 (component, model_assets, embedded, model_diagnostics)。
    """
    if not (embed_model and fetch is not None):
        return replace(component, models=(), model_assets=()), None, False, []

    from lcsc3d.core.errors import DownloadError

    model_uuid = find_model_uuid(component_data)
    if model_uuid is None:
        note('      · 该器件无关联 3D 模型，PcbLib 不含内嵌模型')
        return replace(component, models=(), model_assets=()), None, False, []

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
        return replace(component, models=(), model_assets=()), None, False, []

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
            component, _step_fetch, check, prepare_altium=True, origin_fetch=_origin_fetch)
        embedded = any(m.transform for m in component.models)
        diagnostics = [str(d.message) for d in component.diagnostics
                       if d.domain == 'model3d' and d.severity in ('error', 'warning')]
        if embedded:
            note('      · 3D 模型已按官方放置参数就位，嵌入 PcbLib')
            return component, payloads, True, diagnostics
        note('      · 3D 模型放置参数不可用，PcbLib 不内嵌模型')
        return component, payloads, False, diagnostics
    except Exception as exc:  # noqa: BLE001 - 内嵌失败时降级为普通导出
        note(f'      · 3D 内嵌准备失败，降级为普通 PcbLib（{exc}）')
        return (replace(component, models=(), model_assets=()), None, False,
                [f'{type(exc).__name__}: {exc}'])


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

    check = check_cancelled or (lambda: None)
    note = log or (lambda message: None)

    from lcsc3d.eda.altium import export_schlib, export_pcblib
    from lcsc3d.core.errors import DownloadError

    component = _parse_component_checked(component_data, part, check)

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

    component, model_assets, embedded, model_diagnostics = _resolve_embedding(
        component, component_data, part, check,
        embed_model=embed_model, fetch=fetch, note=note)

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


class AdLibraryMerger:
    """多器件 AD 库合并器：把一个批次的器件合并为单个 SchLib + 单个 PcbLib。

    · 相同封装自动去重（plan_footprints），符号的 Footprint 字段指向最终封装名；
    · 支持 3D 模型内嵌（与单器件导出相同的资源链路）；
    · build() 固定先构建 PcbLib、再以最终封装名构建 SchLib（与上游一致）。

    用法::

        merger = AdLibraryMerger(embed_model=True, fetch=fetch, log=print)
        for code, data in parts:
            merger.add(data, code)          # 单个器件失败会 raise AdExportError
        result = merger.build(out_dir)      # -> LCSC3D.SchLib + LCSC3D.PcbLib
    """

    def __init__(self, *, embed_model=True, model_layer=1, fetch=None, log=None):
        try:
            import olefile  # noqa: F401  合并功能需要（读取/去重库条目）
        except ImportError as exc:
            raise AdExportError('合并库功能需要 olefile 库，请先安装：pip install olefile') from exc
        self.embed_model = bool(embed_model)
        self.model_layer = model_layer
        self.fetch = fetch
        self._note = log or (lambda message: None)
        self._sch = None
        self._pcb = None
        self.parts = []
        self.info = {}

    def add(self, component_data, part, check_cancelled=None):
        """加入一个器件。失败时抛出 AdExportError（不影响已加入的器件）。"""
        check = check_cancelled or (lambda: None)
        if part in self.parts:
            raise AdExportError(f'编号 {part} 重复加入')

        from lcsc3d.eda.altium import MergedLibrary

        component = _parse_component_checked(component_data, part, check)
        component, model_assets, embedded, mdiag = _resolve_embedding(
            component, component_data, part, check,
            embed_model=self.embed_model, fetch=self.fetch, note=self._note)

        if self._sch is None:
            self._sch = MergedLibrary('SCHLIB', merge_pcb=True, symbol_style='jlc',
                                      model_layer=self.model_layer)
            self._pcb = MergedLibrary('PCBLIB', merge_pcb=True, symbol_style='jlc',
                                      model_layer=self.model_layer)

        try:
            self._sch.add(component, part, check)
        except Exception as exc:  # noqa: BLE001
            raise AdExportError(f'符号合并失败：{exc}') from exc
        try:
            self._pcb.add(component, part, check, model_assets=model_assets)
        except Exception as exc:  # noqa: BLE001 - 回滚已加入的符号
            self._sch.entries.pop(part, None)
            raise AdExportError(f'封装合并失败：{exc}') from exc

        self.parts.append(part)
        self.info[part] = {
            'symbol_name': component.symbol.name,
            'footprint_name': component.footprint.name,
            'embedded': embedded,
            'model_diagnostics': mdiag,
        }
        return self.info[part]

    def build(self, out_dir, base_name='LCSC3D', check_cancelled=None):
        """构建并写出合并库。返回 {schlib, pcblib, count, schlib_size, pcblib_size}。"""
        check = check_cancelled or (lambda: None)
        if not self.parts:
            raise AdExportError('没有可合并的器件')
        base_name = _safe_filename(base_name, 'LCSC3D')

        try:
            check()
            pcblib_bytes = self._pcb.build(list(self.parts), check)
            check()
            footprint_names = dict(self._pcb.footprint_names)
            schlib_bytes = self._sch.build(list(self.parts), check,
                                           footprint_names=footprint_names)
        except AdExportError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AdExportError(f'合并构建失败：{type(exc).__name__}: {exc}') from exc

        os.makedirs(out_dir, exist_ok=True)
        schlib_path = os.path.join(out_dir, f'{base_name}.SchLib')
        pcblib_path = os.path.join(out_dir, f'{base_name}.PcbLib')
        with open(schlib_path, 'wb') as f:
            f.write(schlib_bytes)
        with open(pcblib_path, 'wb') as f:
            f.write(pcblib_bytes)

        return {'schlib': schlib_path, 'pcblib': pcblib_path, 'count': len(self.parts),
                'schlib_size': len(schlib_bytes), 'pcblib_size': len(pcblib_bytes),
                'footprint_names': footprint_names}
