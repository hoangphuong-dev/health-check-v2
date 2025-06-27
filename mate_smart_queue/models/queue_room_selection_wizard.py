# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

HIS_PATIENT = 'his.patient'
MATE_QUEUE_TOKEN = "mate.queue.token"
HR_DEPARTMENT = 'hr.department'
PRODUCT_PRODUCT = 'product.product'

MATE_QUEUE_ROOM_SELECTION_WIRARD = 'mate.queue.room.selection.wizard'
MATE_QUEUE_ROOM_SELECTION_LINE = 'mate.queue.room.selection.line'


class QueueRoomSelectionWizard(models.TransientModel):
    _name = MATE_QUEUE_ROOM_SELECTION_WIRARD
    _description = _('Queue Room Selection Wizard')

    patient_id = fields.Many2one(HIS_PATIENT, string=_('Patient'), required=True)
    service_id = fields.Many2one(PRODUCT_PRODUCT, string=_('Service'), required=True)
    current_room_id = fields.Many2one(HR_DEPARTMENT, string=_('Current Room'))
    selected_room_id = fields.Many2one(HR_DEPARTMENT, string=_('Selected Room'), required=True)
    room_line_ids = fields.One2many(MATE_QUEUE_ROOM_SELECTION_LINE, 'wizard_id', string=_('Room List'))
    # Thêm field coordination_type
    coordination_type = fields.Selection([
        ('room_change', _('Change room same service')),
        ('service_room_change', _('Change room for service'))
    ], default='room_change', string=_('Coordination Type'))

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        # Get từ context với prefix 'default_'
        patient_id = self.env.context.get('default_patient_id') or self.env.context.get('patient_id')
        service_id = self.env.context.get('default_service_id') or self.env.context.get('service_id')
        current_room_id = self.env.context.get('default_current_room_id') or self.env.context.get('current_room_id')
        coordination_type = self.env.context.get('default_coordination_type') or self.env.context.get(
            'coordination_type', 'room_change')

        if patient_id:
            defaults['patient_id'] = patient_id
        if service_id:
            defaults['service_id'] = service_id
        if current_room_id:
            defaults['current_room_id'] = current_room_id
        defaults['coordination_type'] = coordination_type

        return defaults

    @api.model
    def create(self, vals):
        wizard = super().create(vals)
        wizard._populate_room_lines()
        return wizard

    @api.onchange('service_id')
    def _onchange_service_id(self):
        """Populate room lines when service changes"""
        if self.service_id:
            self._populate_room_lines()

    def _populate_room_lines(self):
        """Populate available rooms for the service"""
        self.room_line_ids = [(5, 0, 0)]  # Clear existing lines

        if not self.service_id:
            return

        # Find all open rooms for this service
        available_rooms = self.env[HR_DEPARTMENT].search([
            ('service_id', '=', self.service_id.id),
            ('state', '=', 'open')
        ])

        if not available_rooms:
            return

        # Find least loaded room
        least_loaded_room = self._find_least_loaded_room(available_rooms)

        # Create lines for each room
        lines = []
        for room in available_rooms:
            queue_info = self._get_room_queue_info(room)

            line_vals = {
                'room_id': room.id,
                'waiting_count': queue_info['waiting_count'],
                'estimated_wait_time': queue_info['estimated_wait_time'],
                'is_current': room.id == self.current_room_id.id if self.current_room_id else False,
                'is_recommended': room.id == least_loaded_room.id if least_loaded_room else False,
            }
            lines.append((0, 0, line_vals))

        self.room_line_ids = lines

    def _find_least_loaded_room(self, rooms):
        """Find room with least load"""
        least_loaded_room = None
        min_load = float('inf')

        for room in rooms:
            waiting_count = self.env[MATE_QUEUE_TOKEN].search_count([
                ('room_id', '=', room.id),
                ('state', '=', 'waiting')
            ])

            load_ratio = waiting_count / room.capacity if room.capacity > 0 else float('inf')

            if load_ratio < min_load:
                min_load = load_ratio
                least_loaded_room = room

        return least_loaded_room

    def _get_room_queue_info(self, room):
        """Get real-time queue info for room"""
        waiting_tokens = self.env[MATE_QUEUE_TOKEN].search([
            ('room_id', '=', room.id),
            ('state', '=', 'waiting')
        ])

        waiting_count = len(waiting_tokens)

        # Calculate estimated wait time
        if waiting_count == 0:
            estimated_wait_time = 0
        else:
            # Simple estimation: count * average service duration
            avg_duration = room.service_id.average_duration or 15  # default 15 minutes
            estimated_wait_time = waiting_count * avg_duration

        return {
            'waiting_count': waiting_count,
            'estimated_wait_time': estimated_wait_time
        }

    def action_coordinate(self):
        """Thực hiện điều phối chuyển phòng"""
        if not self.selected_room_id:
            raise UserError(_('Please select a room to transfer to'))

        if self.selected_room_id.id == self.current_room_id.id:
            raise UserError(_('Selected room is the same as current room'))

        # Xử lý theo coordination_type
        if self.coordination_type == 'service_room_change':
            result = self.patient_id.with_context(
                target_room_id=self.selected_room_id.id,
                target_service_id=self.service_id.id,
                coordination_type='service_room_selection'
            ).action_coordinate_service_room()
        else:
            # Đổi phòng thông thường
            result = self.patient_id.with_context(
                target_room_id=self.selected_room_id.id,
                coordination_type='room_change'
            ).action_coordinate_room()

        return result


class QueueRoomSelectionLine(models.TransientModel):
    _name = MATE_QUEUE_ROOM_SELECTION_LINE
    _description = _('Queue Room Selection Line')

    wizard_id = fields.Many2one(MATE_QUEUE_ROOM_SELECTION_WIRARD, string=_('Wizard'), ondelete='cascade')
    room_id = fields.Many2one(HR_DEPARTMENT, string=_('Room'), required=True)
    waiting_count = fields.Integer(string=_('Waiting Count'))
    estimated_wait_time = fields.Float(string=_('Estimated Wait Time (minutes)'))
    is_current = fields.Boolean(string=_('Current Room'))
    is_recommended = fields.Boolean(string=_('Recommended'))

    # Computed fields for UI
    wait_time_color = fields.Selection([
        ('green', _('Green')),
        ('orange', _('Orange')),
        ('red', _('Red'))
    ], compute='_compute_wait_time_color')

    wait_time_text = fields.Char(compute='_compute_wait_time_text')

    @api.depends('estimated_wait_time')
    def _compute_wait_time_color(self):
        for line in self:
            if line.estimated_wait_time < 25:
                line.wait_time_color = 'green'
            elif line.estimated_wait_time <= 45:
                line.wait_time_color = 'orange'
            else:
                line.wait_time_color = 'red'

    @api.depends('estimated_wait_time')
    def _compute_wait_time_text(self):
        for line in self:
            if line.estimated_wait_time == 0:
                line.wait_time_text = _('0 minutes')
            else:
                line.wait_time_text = _('%d minutes') % int(line.estimated_wait_time)
