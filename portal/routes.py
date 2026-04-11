"""
Product Pipeline Portal — Blueprint routes for unified server
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
import tempfile
from datetime import datetime

from flask import Blueprint, render_template, jsonify, request, send_file, abort
from werkzeug.utils import secure_filename

import config
from portal.database_manager import PortfolioDatabase
from portal.excel_parser import ExcelParser
from portal.priority_parser import parse_priority_list

portal_pages = Blueprint('portal_pages', __name__)
portal_api   = Blueprint('portal_api',   __name__)

db = PortfolioDatabase()


# ══════════════════════════════════════════════════════════════════════════════
# PAGES
# ══════════════════════════════════════════════════════════════════════════════

@portal_pages.route('/')
def index():
    projects  = db.get_all_portfolio_projects()
    snapshots = db.get_snapshots()
    return render_template('portal/index.html',
                           projects=projects,
                           snapshots=snapshots,
                           disciplines=config.DISCIPLINES,
                           today=datetime.now().strftime('%Y-%m-%d'))


@portal_pages.route('/project/<int:project_id>')
def project_detail(project_id):
    pp = db.get_portfolio_project(project_id)
    if not pp:
        abort(404)
    if pp['management_type'] == 'gantt':
        # Find linked gantt project
        conn = db.get_connection()
        c = conn.cursor()
        c.execute('SELECT p.* FROM projects p JOIN portfolio_projects pp ON pp.project_id = p.id WHERE pp.id = ?', (project_id,))
        gp = c.fetchone()
        conn.close()
        if gp:
            return render_template('portal/gantt.html',
                                   pp=pp,
                                   project_name=gp['name'],
                                   project_manager=gp['manager'],
                                   gantt_project_id=gp['id'],
                                   disciplines=config.DISCIPLINES,
                                   today=datetime.now().strftime('%Y-%m-%d'))
    # Card view
    card      = db.get_card_data(project_id)
    actions   = db.get_action_items(project_id)
    risks     = db.get_risks(project_id)
    certs     = db.get_certifications(project_id)
    updates   = db.get_updates_log(project_id)
    resources = db.get_project_resources(project_id)
    return render_template('portal/project_detail.html',
                           pp=pp,
                           card=card,
                           actions=actions,
                           risks=risks,
                           certs=certs,
                           updates=updates,
                           resources=resources,
                           disciplines=config.DISCIPLINES,
                           today=datetime.now().strftime('%Y-%m-%d'))


@portal_pages.route('/settings')
def settings():
    mappings = db.get_all_discipline_map_rows()
    return render_template('portal/settings.html',
                           mappings=mappings,
                           disciplines=config.DISCIPLINES)


# ══════════════════════════════════════════════════════════════════════════════
# API — PORTFOLIO PROJECTS
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects')
def api_portfolio_projects():
    return jsonify(db.get_all_portfolio_projects())


@portal_api.route('/api/portfolio/projects', methods=['POST'])
def api_create_project():
    data = request.json or {}
    if not data.get('name'):
        return jsonify({'error': 'name required'}), 400
    pid = db.upsert_portfolio_project(data)
    # Ensure resource rows exist for all disciplines
    for disc in config.DISCIPLINES:
        db.upsert_project_resource(pid, disc, coverage='N/A', demand_days=0)
    return jsonify({'id': pid, 'ok': True}), 201


@portal_api.route('/api/portfolio/projects/<int:pid>', methods=['PATCH'])
def api_update_project(pid):
    data = request.json or {}
    db.update_portfolio_project(pid, data)
    return jsonify({'ok': True})


@portal_api.route('/api/portfolio/projects/<int:pid>', methods=['DELETE'])
def api_delete_portfolio_project(pid):
    db.delete_portfolio_project(pid)
    return jsonify({'ok': True})


# ── Priority reorder ─────────────────────────────────────────────────────────

@portal_api.route('/api/portfolio/reorder', methods=['POST'])
def api_reorder():
    data = request.json or {}
    ordered_ids = data.get('ordered_ids', [])
    changed_by  = data.get('changed_by', 'PM')
    if not ordered_ids:
        return jsonify({'error': 'ordered_ids required'}), 400
    db.reorder_priorities(ordered_ids, changed_by)
    return jsonify({'ok': True})


# ── Priority import preview (from Excel) ──────────────────────────────────────

@portal_api.route('/api/portfolio/import-preview', methods=['POST'])
def api_import_preview():
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    if not f.filename.endswith('.xlsx'):
        return jsonify({'error': 'xlsx required'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    f.save(tmp.name)
    tmp.close()

    try:
        parsed = parse_priority_list(tmp.name)
    finally:
        os.unlink(tmp.name)

    # Compare with existing portfolio
    existing = {p['name']: p for p in db.get_all_portfolio_projects()}
    changes  = []
    for p in parsed['big_projects']:
        ex = existing.get(p['name'])
        if ex is None:
            changes.append({'action': 'add', 'project': p})
        else:
            diffs = {}
            for field in ('priority', 'leader', 'next_gate', 'planned_launch', 'objective'):
                if str(ex.get(field, '')) != str(p.get(field, '')):
                    diffs[field] = {'old': ex.get(field), 'new': p.get(field)}
            if diffs:
                changes.append({'action': 'update', 'project': p, 'diffs': diffs, 'id': ex['id']})

    return jsonify({'sheet': parsed['sheet'], 'changes': changes,
                    'small_projects': parsed['small_projects'],
                    'on_hold': parsed['on_hold'], 'proposed': parsed['proposed']})


@portal_api.route('/api/portfolio/import-apply', methods=['POST'])
def api_import_apply():
    data    = request.json or {}
    changes = data.get('changes', [])
    applied = 0
    for ch in changes:
        if not ch.get('approved'):
            continue
        p      = ch['project']
        action = ch['action']
        if action == 'add':
            pid = db.upsert_portfolio_project(p)
            for disc in config.DISCIPLINES:
                res = p.get('resources', {}).get(disc, {})
                db.upsert_project_resource(pid, disc,
                    coverage=res.get('coverage', 'N/A'),
                    demand_days=res.get('demand_days', 0),
                    is_manual_override=1)
        elif action == 'update':
            db.update_portfolio_project(ch['id'], p)
            for disc in config.DISCIPLINES:
                res = p.get('resources', {}).get(disc, {})
                db.upsert_project_resource(ch['id'], disc,
                    coverage=res.get('coverage', 'N/A'),
                    demand_days=res.get('demand_days', 0))
        applied += 1

    # Save snapshot
    db.save_snapshot(source='excel_import')
    return jsonify({'ok': True, 'applied': applied})


# ── Management type switch ────────────────────────────────────────────────────

@portal_api.route('/api/portfolio/projects/<int:pid>/set-type', methods=['POST'])
def api_set_management_type(pid):
    data = request.json or {}
    mtype = data.get('management_type', 'card')
    if mtype not in ('gantt', 'card'):
        return jsonify({'error': 'invalid type'}), 400
    db.update_portfolio_project(pid, {'management_type': mtype})
    return jsonify({'ok': True})


# ── Portfolio overview (resource table) ───────────────────────────────────────

@portal_api.route('/api/portfolio/overview')
def api_portfolio_overview():
    return jsonify(db.get_portfolio_overview())


@portal_api.route('/api/portfolio/gate-timeline')
def api_gate_timeline():
    return jsonify(db.get_overall_gate_timeline())


# ── Snapshots ────────────────────────────────────────────────────────────────

@portal_api.route('/api/portfolio/snapshots', methods=['GET'])
def api_snapshots():
    return jsonify(db.get_snapshots())


@portal_api.route('/api/portfolio/snapshots', methods=['POST'])
def api_create_snapshot():
    db.save_snapshot(source='manual')
    return jsonify({'ok': True})


@portal_api.route('/api/portfolio/snapshots/<int:sid>')
def api_get_snapshot(sid):
    snap = db.get_snapshot(sid)
    if not snap:
        abort(404)
    return jsonify({'id': snap['id'], 'snapshot_date': snap['snapshot_date'],
                    'source': snap['source'], 'created_at': snap['created_at'],
                    'data': json.loads(snap['data_json'])})


# ══════════════════════════════════════════════════════════════════════════════
# API — GANTT
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/gantt/import', methods=['POST'])
def api_gantt_import():
    """Import a Gantt Excel file for a portfolio project."""
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    portfolio_project_id = request.form.get('portfolio_project_id')
    if not portfolio_project_id:
        return jsonify({'error': 'portfolio_project_id required'}), 400
    pid = int(portfolio_project_id)

    f = request.files['file']
    if not f.filename.endswith('.xlsx'):
        return jsonify({'error': 'xlsx required'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    f.save(tmp.name)
    tmp.close()

    try:
        parser = ExcelParser()
        project_info, tasks = parser.parse_excel_file(tmp.name)
    finally:
        os.unlink(tmp.name)

    # Create/update gantt project
    gantt_pid = db.create_or_update_gantt_project(
        pid, project_info['name'], project_info['manager'], f.filename)

    # Insert tasks
    db.insert_tasks_bulk(gantt_pid, tasks)

    # Auto-detect dependencies (finish-to-start, ≤2 day gap)
    _auto_detect_dependencies(gantt_pid, project_info['name'])

    # Set gate baselines
    all_tasks = db.get_tasks(gantt_pid)
    for t in all_tasks:
        if t['milestone'] and t['end_date']:
            db.set_gate_baseline(project_info['name'], t['name'], t['id'], t['end_date'])

    # Switch management type to gantt
    db.update_portfolio_project(pid, {'management_type': 'gantt'})

    # Compute resource aggregation
    db.compute_and_store_gantt_resources(pid, gantt_pid)

    return jsonify({'ok': True, 'gantt_project_id': gantt_pid,
                    'project_name': project_info['name'], 'task_count': len(tasks)})


def _auto_detect_dependencies(gantt_project_id, project_name):
    """Create dependencies for tasks with finish-to-start gap ≤2 days."""
    from datetime import date as _date
    tasks = db.get_tasks(gantt_project_id)
    conn = db.get_connection()
    conn.execute('DELETE FROM task_dependencies WHERE project_name = ?', (project_name,))
    conn.commit()
    conn.close()

    for a in tasks:
        if not a.get('end_date'):
            continue
        try:
            a_end = _date.fromisoformat(a['end_date'])
        except Exception:
            continue
        for b in tasks:
            if a['id'] == b['id'] or not b.get('start_date'):
                continue
            try:
                b_start = _date.fromisoformat(b['start_date'])
            except Exception:
                continue
            delta = (b_start - a_end).days
            if 0 <= delta <= 2:
                db.add_dependency(project_name, a['id'], b['id'])


@portal_api.route('/api/project/<project_name>/tasks')
def api_get_tasks(project_name):
    gp = db.get_project_by_name(project_name)
    if not gp:
        return jsonify([])
    return jsonify(db.get_tasks(gp['id']))


@portal_api.route('/api/project/<project_name>/dependencies')
def api_get_dependencies(project_name):
    return jsonify(db.get_dependencies(project_name))


@portal_api.route('/api/project/<project_name>/task', methods=['POST'])
def api_create_task(project_name):
    gp = db.get_project_by_name(project_name)
    if not gp:
        abort(404)
    data   = request.json or {}
    new_id = db.create_task(gp['id'], data)
    _recompute_resources(gp)
    return jsonify({'id': new_id, 'ok': True}), 201


@portal_api.route('/api/project/<project_name>/task/<int:task_id>', methods=['PUT'])
def api_update_task(project_name, task_id):
    gp = db.get_project_by_name(project_name)
    if not gp:
        abort(404)
    data = request.json or {}

    # Gate change log
    old_task = db.get_task(task_id)
    if old_task and old_task.get('milestone') and data.get('end_date'):
        old_date = old_task.get('end_date', '')
        new_date = data.get('end_date', '')
        if old_date and new_date and old_date != new_date:
            baseline = next((b['baseline_date'] for b in db.get_gate_baselines(project_name)
                             if b['gate_id'] == task_id), old_date)
            try:
                from datetime import date as _date
                d1 = _date.fromisoformat(old_date)
                d2 = _date.fromisoformat(new_date)
                days = (d2 - d1).days
            except Exception:
                days = 0
            db.log_gate_change(project_name, old_task['name'], task_id,
                               baseline, old_date, new_date, days)

    db.update_task(task_id, data)

    if 'predecessor_ids' in data:
        db.set_dependencies_for_task(project_name, task_id, data['predecessor_ids'])

    _recompute_resources(gp)
    return jsonify({'ok': True})


@portal_api.route('/api/project/<project_name>/task/<int:task_id>', methods=['DELETE'])
def api_delete_task(project_name, task_id):
    gp = db.get_project_by_name(project_name)
    if not gp:
        abort(404)
    db.delete_task(task_id)
    _recompute_resources(gp)
    return jsonify({'ok': True})


@portal_api.route('/api/project/<project_name>/dependencies', methods=['POST'])
def api_add_dependency(project_name):
    data = request.json or {}
    db.add_dependency(project_name, data['predecessor_id'], data['successor_id'])
    return jsonify({'ok': True})


@portal_api.route('/api/project/<project_name>/dependencies/<int:dep_id>', methods=['DELETE'])
def api_delete_dependency(project_name, dep_id):
    db.delete_dependency(dep_id)
    return jsonify({'ok': True})


@portal_api.route('/api/project/<project_name>/gate-baselines')
def api_gate_baselines(project_name):
    return jsonify(db.get_gate_baselines(project_name))


@portal_api.route('/api/project/<project_name>/gate-change-log')
def api_gate_change_log(project_name):
    return jsonify(db.get_gate_change_log(project_name))


@portal_api.route('/api/project/<project_name>/gate-sign-offs')
def api_get_gate_sign_offs(project_name):
    return jsonify(db.get_gate_sign_offs(project_name))


@portal_api.route('/api/project/<project_name>/gate-sign-off', methods=['POST'])
def api_gate_sign_off(project_name):
    data = request.json or {}
    db.set_gate_sign_off(project_name, data['gate_name'], data['gate_id'],
                         data['sign_off_date'], data['status'],
                         data.get('rework_due_date'))
    return jsonify({'ok': True})


def _recompute_resources(gp):
    """Recompute gantt resources for a project after any task change."""
    try:
        pid = gp.get('portfolio_project_id') or gp.get('id')
        db.compute_and_store_gantt_resources(pid, gp['id'] if 'id' in gp else None)
    except Exception as e:
        print(f'[WARN] Resource recompute failed: {e}')


# ══════════════════════════════════════════════════════════════════════════════
# API — CARD DATA
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects/<int:pid>/card', methods=['GET'])
def api_get_card(pid):
    return jsonify(db.get_card_data(pid))


@portal_api.route('/api/portfolio/projects/<int:pid>/card', methods=['PUT'])
def api_update_card(pid):
    db.upsert_card_data(pid, request.json or {})
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# API — ACTION ITEMS
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects/<int:pid>/actions')
def api_get_actions(pid):
    return jsonify(db.get_action_items(pid))


@portal_api.route('/api/portfolio/projects/<int:pid>/actions', methods=['POST'])
def api_create_action(pid):
    new_id = db.create_action_item(pid, request.json or {})
    return jsonify({'id': new_id, 'ok': True}), 201


@portal_api.route('/api/portfolio/projects/<int:pid>/actions/<int:aid>', methods=['PATCH'])
def api_update_action(pid, aid):
    db.update_action_item(aid, request.json or {})
    return jsonify({'ok': True})


@portal_api.route('/api/portfolio/projects/<int:pid>/actions/<int:aid>', methods=['DELETE'])
def api_delete_action(pid, aid):
    db.delete_action_item(aid)
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# API — RISKS
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects/<int:pid>/risks')
def api_get_risks(pid):
    return jsonify(db.get_risks(pid))


@portal_api.route('/api/portfolio/projects/<int:pid>/risks', methods=['POST'])
def api_create_risk(pid):
    new_id = db.create_risk(pid, request.json or {})
    return jsonify({'id': new_id, 'ok': True}), 201


@portal_api.route('/api/portfolio/projects/<int:pid>/risks/<int:rid>', methods=['PATCH'])
def api_update_risk(pid, rid):
    db.update_risk(rid, request.json or {})
    return jsonify({'ok': True})


@portal_api.route('/api/portfolio/projects/<int:pid>/risks/<int:rid>', methods=['DELETE'])
def api_delete_risk(pid, rid):
    db.delete_risk(rid)
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# API — CERTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects/<int:pid>/certs')
def api_get_certs(pid):
    return jsonify(db.get_certifications(pid))


@portal_api.route('/api/portfolio/projects/<int:pid>/certs', methods=['POST'])
def api_create_cert(pid):
    new_id = db.create_certification(pid, request.json or {})
    return jsonify({'id': new_id, 'ok': True}), 201


@portal_api.route('/api/portfolio/projects/<int:pid>/certs/<int:cid>', methods=['PATCH'])
def api_update_cert(pid, cid):
    db.update_certification(cid, request.json or {})
    return jsonify({'ok': True})


@portal_api.route('/api/portfolio/projects/<int:pid>/certs/<int:cid>', methods=['DELETE'])
def api_delete_cert(pid, cid):
    db.delete_certification(cid)
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# API — UPDATES LOG
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects/<int:pid>/updates')
def api_get_updates(pid):
    return jsonify(db.get_updates_log(pid))


@portal_api.route('/api/portfolio/projects/<int:pid>/updates', methods=['POST'])
def api_add_update(pid):
    data = request.json or {}
    db.add_update(pid, data.get('author', ''), data.get('content', ''))
    return jsonify({'ok': True}), 201


@portal_api.route('/api/portfolio/projects/<int:pid>/updates/<int:uid>', methods=['DELETE'])
def api_delete_update(pid, uid):
    db.delete_update(uid)
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# API — RESOURCES
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects/<int:pid>/resources')
def api_get_resources(pid):
    return jsonify(db.get_project_resources(pid))


@portal_api.route('/api/portfolio/projects/<int:pid>/resources', methods=['PUT'])
def api_set_resources(pid):
    items = request.json or []
    for item in items:
        db.set_manual_resource_override(pid, item['discipline'],
                                        item.get('coverage', 'N/A'),
                                        item.get('demand_days', 0))
    return jsonify({'ok': True})


@portal_api.route('/api/portfolio/projects/<int:pid>/resources/recompute', methods=['POST'])
def api_recompute_resources(pid):
    conn = db.get_connection()
    c = conn.cursor()
    c.execute('SELECT p.id FROM projects p JOIN portfolio_projects pp ON pp.project_id = p.id WHERE pp.id = ?', (pid,))
    gp = c.fetchone()
    conn.close()
    if not gp:
        return jsonify({'error': 'no gantt project linked'}), 400
    db.compute_and_store_gantt_resources(pid, gp['id'])
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# API — SETTINGS (discipline mapping)
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/settings/discipline-map')
def api_get_discipline_map():
    return jsonify(db.get_all_discipline_map_rows())


@portal_api.route('/api/settings/discipline-map', methods=['PUT'])
def api_set_discipline_map():
    mappings = request.json or []
    db.set_discipline_map(mappings)
    return jsonify({'ok': True})


@portal_api.route('/api/settings/discipline-map', methods=['POST'])
def api_add_discipline_map():
    data = request.json or {}
    db.add_discipline_mapping(data.get('owner_name', ''), data.get('discipline', ''))
    return jsonify({'ok': True})


@portal_api.route('/api/settings/discipline-map/<int:mid>', methods=['DELETE'])
def api_delete_discipline_map(mid):
    db.delete_discipline_mapping(mid)
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE GENERATION
# ══════════════════════════════════════════════════════════════════════════════

@portal_api.route('/api/portfolio/projects/<int:pid>/generate-slide')
def api_generate_slide(pid):
    from portal.ppt_exporter import generate_project_slide
    pp      = db.get_portfolio_project(pid)
    if not pp:
        abort(404)
    risks   = db.get_risks(pid)
    certs   = db.get_certifications(pid)
    updates = db.get_updates_log(pid, limit=10)
    resources = db.get_project_resources(pid)

    tasks   = []
    actions = db.get_action_items(pid)
    if pp['management_type'] == 'gantt':
        conn = db.get_connection()
        c = conn.cursor()
        c.execute('SELECT p.id FROM projects p JOIN portfolio_projects pp ON pp.project_id = p.id WHERE pp.id = ?', (pid,))
        gp = c.fetchone()
        conn.close()
        if gp:
            tasks = db.get_tasks(gp['id'])

    out_path = config.EXCEL_OUTPUT_FOLDER / f'{_safe_name(pp["name"])}_slide.pptx'
    generate_project_slide(pp, tasks=tasks,
                           actions=actions,
                           risks=risks, certs=certs, updates=updates,
                           resources=resources, out_path=str(out_path))

    return send_file(str(out_path), as_attachment=True,
                     download_name=f'{_safe_name(pp["name"])}_status.pptx')


def _safe_name(s):
    return ''.join(c if c.isalnum() or c in ' _-' else '_' for c in s)[:60]


def register_portal(app):
    db.initialize_database()
    app.register_blueprint(portal_pages, url_prefix='/portal')
    app.register_blueprint(portal_api)   # no prefix — API stays at /api/...
