"""Render readable, local Markdown indexes from a VISUAL-02 JSON census."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from tools.visual02_paths import safe_evidence_output

MAX_INPUT = 128 * 1024 * 1024


def alpha_description(dds):
    if not dds:
        return 'не проверено'
    values = dds['alpha_values_top_mip']
    if values == [255]:
        return 'верхний mip: только 255'
    if set(values).issubset({0, 255}):
        return 'верхний mip: 0/255'
    return f'верхний mip: {len(values)} значений'


def render(data):
    if data.get('schema') != 'wot091-visual02-soviet-textures.v1':
        raise ValueError('unexpected inventory schema')
    textures = {x['resource'].casefold(): x for x in data['textures']}
    tree_ids = {v['vehicle_id'] for v in data['vehicles'] if v['reachable_from_ms1_in_client_research_graph']}
    head = ('# Опись советских текстур #717\n\n'
            'Только статические пути неповреждённых моделей и родительских LOD из архивов; '
            'runtime, активные подмены и видимость ветки в UI отдельно не проверены. '
            'Альфа исследована только в верхнем mip, её назначение UNKNOWN. '
            'Поиск в архивах без учёта регистра; поведение ResMgr не проверено.\n\n')
    vehicle_lines = [head, '## Машины и цветовые карты\n\n',
                     'Дерево: достижимость из МС-1 по статическому графу, без проверки предусловий.\n\n',
                     '| Машина | Уровень | Дерево | Цветовые карты: файл, формат, альфа | Замечания |\n',
                     '|---|---:|---|---|---:|\n']
    for v in data['vehicles']:
        names = sorted({b['texture'].casefold() for b in v['bindings'] if b['role'] == 'diffuse'})
        cells = []
        for name in names:
            t = textures[name]; d = t['dds'] or {}
            cells.append('`' + t['resource'] + '` (' + d.get('format', '?') + '; ' + alpha_description(t['dds']) + ')')
        vehicle_lines.append(f"| `{v['vehicle_id']}` | {v['tier']} | "
                             f"{'да' if v['reachable_from_ms1_in_client_research_graph'] else 'нет'} | "
                             f"{'<br>'.join(cells) or 'нет подтверждённой ссылки'} | {len(v['unresolved'])} |\n")
    vehicle_lines.append('\nПодробные причины замечаний, model/visual/property, archive/member, хеши и другие роли — в `inventory.json`.\n')
    texture_lines = [head, '## Ресурсы и материалы\n\n',
                     'Один файл может использоваться несколькими машинами или ролями; '
                     'список машин ниже включает дерево и остальные записи.\n\n',
                     '| Текстура | Формат | Размер | Mip | Альфа верхнего mip | Роли | Машины |\n',
                     '|---|---|---|---:|---|---|---|\n']
    for t in data['textures']:
        d = t['dds'] or {}
        roles = ', '.join(sorted({u['property'] for u in t['uses']}))
        names = ', '.join('`' + u + ('*' if u in tree_ids else '') + '`' for u in sorted({u['vehicle_id'] for u in t['uses']}))
        dims = f"{d['width']}×{d['height']}" if d else '?'
        texture_lines.append(f"| `{t['resource']}` | {d.get('format', '?')} | {dims} | {d.get('mip_count', '?')} | "
                             f"{alpha_description(t['dds'])} | {roles} | {names} |\n")
    texture_lines.append('\n`*` — статически достижима из МС-1. Разбор роли альфа-канала и другие mip — UNKNOWN.\n')
    groups = defaultdict(list)
    for t in data['textures']:
        tree_uses = {u['vehicle_id'] for u in t['uses'] if u['vehicle_id'] in tree_ids and u['role'] == 'diffuse'}
        if tree_uses:
            d = t['dds'] or {}
            vals = d.get('alpha_values_top_mip')
            alpha_group = ('альфа неизвестна' if vals is None else
                           'альфа верхнего mip только 255' if vals == [255] else
                           'альфа верхнего mip 0/255' if set(vals).issubset({0, 255}) else
                           'переменная альфа верхнего mip')
            key = (d.get('format', 'UNKNOWN'), alpha_group)
            groups[key].append((t, tree_uses))
    group_lines = [head, '## Цветовые текстуры статического дерева\n\n',
                   'Это группировка для подготовки, не допуск к автоматической обработке. '
                   'Текстуры нормалей и материалов сюда не включены.\n\n']
    for (fmt, alpha), items in sorted(groups.items()):
        group_lines.append(f'### {fmt}; {alpha} — {len(items)} файлов\n\n')
        group_lines.append('| Текстура | Размер | Mip | Машины в статическом дереве |\n|---|---|---:|---|\n')
        for t, uses in items:
            d = t['dds'] or {}
            dims = f"{d['width']}×{d['height']}" if d else '?'
            names = ', '.join('`' + x + '`' for x in sorted(uses))
            group_lines.append(f"| `{t['resource']}` | {dims} | {d.get('mip_count', '?')} | {names} |\n")
        group_lines.append('\n')
    return ''.join(vehicle_lines), ''.join(texture_lines), ''.join(group_lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory', required=True, type=Path)
    p.add_argument('--out-dir', required=True, type=Path)
    args = p.parse_args()
    with args.inventory.open('rb') as f:
        raw = f.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError('inventory input bound')
    a, b, c = render(json.loads(raw))
    out_dir = safe_evidence_output(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, contents in [('vehicles.md', a), ('textures.md', b), ('tree-colour-groups.md', c)]:
        payload = contents.encode('utf-8')
        out = safe_evidence_output(out_dir / name)
        with out.open('xb') as f:
            f.write(payload)
        print(name, len(payload), hashlib.sha256(payload).hexdigest())


if __name__ == '__main__':
    main()
