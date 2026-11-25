"""Run inside an Odoo shell against the isolated module test database."""

from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime, timezone
import threading
import uuid

from psycopg2 import IntegrityError

from odoo import api, Command
from odoo.tools import mute_logger


assert env.cr.dbname.startswith('equipment_module_test_'), 'Concurrency fixtures must stay in a test database'
suffix = uuid.uuid4().hex[:8]
manager_group = env.ref('equipment_borrowing.group_equipment_manager')
employee_group = env.ref('base.group_user')
users = env['res.users'].with_context(no_reset_password=True).create([
    {'name': 'Race Manager A', 'login': 'race_manager_a_' + suffix, 'group_ids': [Command.set(manager_group.ids)]},
    {'name': 'Race Manager B', 'login': 'race_manager_b_' + suffix, 'group_ids': [Command.set(manager_group.ids)]},
    {'name': 'Race Employee A', 'login': 'race_employee_a_' + suffix, 'group_ids': [Command.set(employee_group.ids)]},
    {'name': 'Race Employee B', 'login': 'race_employee_b_' + suffix, 'group_ids': [Command.set(employee_group.ids)]},
])
manager_a, manager_b, employee_a, employee_b = users
equipment = env['equipment.borrowing.equipment'].with_user(manager_a).create({
    'name': 'Concurrent approval test item', 'code': 'RACE-' + suffix,
})
request_ids = []
for applicant in (employee_a, employee_b):
    request = env['equipment.borrowing.request'].with_user(applicant).create({
        'equipment_id': equipment.id, 'borrow_date': '2026-12-01',
        'return_date': '2026-12-03', 'reason': 'Concurrent approval verification',
    })
    request.action_submit()
    request_ids.append(request.id)
registry = env.registry
equipment_id = equipment.id
manager_ids = [manager_a.id, manager_b.id]
env.cr.commit()
barrier = threading.Barrier(2)


def approve_in_own_transaction(index):
    with registry.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '15s'")
        actor_env = api.Environment(cursor, manager_ids[index], {})
        request = actor_env['equipment.borrowing.request'].browse(request_ids[index])
        assert request.state == 'pending'
        assert actor_env['equipment.borrowing.request'].search_count([
            ('equipment_id', '=', equipment_id), ('state', 'in', ['approved', 'borrowed']),
        ]) == 0
        # Both transactions establish their snapshots before either approval.
        barrier.wait(timeout=10)
        try:
            with mute_logger('odoo.sql_db'):
                request.action_approve()
            cursor.commit()
            return {'request_id': request_ids[index], 'manager_id': manager_ids[index], 'result': 'approved'}
        except IntegrityError as error:
            constraint = error.diag.constraint_name
            cursor.rollback()
            assert constraint == 'equipment_borrowing_request_active_equipment_unique', constraint
            return {'request_id': request_ids[index], 'manager_id': manager_ids[index], 'result': 'blocked_by_unique_index'}


with ThreadPoolExecutor(max_workers=2) as executor:
    futures = [executor.submit(approve_in_own_transaction, index) for index in range(2)]
    outcomes = [future.result(timeout=25) for future in futures]
assert sorted(item['result'] for item in outcomes) == ['approved', 'blocked_by_unique_index'], outcomes
env.cr.rollback()
env.invalidate_all()
active_count = env['equipment.borrowing.request'].search_count([
    ('equipment_id', '=', equipment_id), ('state', 'in', ['approved', 'borrowed']),
])
assert active_count == 1
winner = next(item for item in outcomes if item['result'] == 'approved')
loser = next(item for item in outcomes if item['result'] != 'approved')
winner_request = env['equipment.borrowing.request'].with_user(env['res.users'].browse(winner['manager_id'])).browse(winner['request_id'])
winner_request.action_borrow()
winner_request.action_return()
loser_request = env['equipment.borrowing.request'].with_user(env['res.users'].browse(loser['manager_id'])).browse(loser['request_id'])
loser_request.action_approve()
env.cr.commit()
report = {
    'checked_at': datetime.now(timezone.utc).isoformat(),
    'module_version': env['ir.module.module'].search([('name', '=', 'equipment_borrowing')], limit=1).latest_version,
    'database': env.cr.dbname, 'independent_transactions': 2,
    'outcomes': outcomes, 'active_requests_after_race': active_count,
    'reapproval_after_return': 'passed', 'result': 'passed',
}
print(json.dumps(report, indent=2))
