/** @odoo-module **/

import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { useService } from "@web/core/utils/hooks";

export class QueueCoordinationKanbanRenderer extends KanbanRenderer {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    /**
     * Override để đảm bảo single column layout
     */
    onMounted() {
        super.onMounted();
        this.ensureSingleColumnLayout();
    }

    /**
     * Đảm bảo layout 1 cột
     */
    ensureSingleColumnLayout() {
        const kanbanGroups = this.el.querySelectorAll('.o_kanban_group');
        kanbanGroups.forEach(group => {
            group.style.width = '100%';
            group.style.maxWidth = '100%';
            group.style.minWidth = '100%';
            group.style.flex = '1 1 100%';
        });
    }

    /**
     * Override sortRecordDrop to handle drag and drop
     */
    async sortRecordDrop(dataRecordId, dataGroupId, { element, parent, previous }) {
        console.log('=== SORT RECORD DROP CALLED ===');
        console.log('Data Record ID:', dataRecordId);
        console.log('Data Group ID:', dataGroupId);

        try {
            const recordId = this._getRecordId(element, dataRecordId);
            const targetGroupId = this._getTargetGroupId(parent, dataGroupId);

            if (!this._validateGroupMove(dataGroupId, targetGroupId)) {
                return;
            }

            const token = await this._getTokenData(recordId);
            if (!this._validateTokenState(token)) {
                return;
            }

            const newPosition = await this._calculateNewPosition(recordId, token, previous);
            await this._performReorder(recordId, token, newPosition);

        } catch (error) {
            await this._handleError(error);
        }
    }

    /**
     * Extract record ID from element
     */
    _getRecordId(element, fallbackId) {
        const recordElement = element.closest('[data-id]');
        const recordId = recordElement ? parseInt(recordElement.dataset.id) : fallbackId;

        if (!recordId) {
            throw new Error('Không thể xác định ID của token');
        }

        console.log('Actual Record ID:', recordId);
        return recordId;
    }

    /**
     * Extract target group ID
     */
    _getTargetGroupId(parent, fallbackGroupId) {
        const targetGroupElement = parent?.closest('[data-id]');
        return targetGroupElement ? targetGroupElement.dataset.id : fallbackGroupId;
    }

    /**
     * Validate if token can be moved between groups
     */
    _validateGroupMove(sourceGroupId, targetGroupId) {
        if (sourceGroupId && targetGroupId && sourceGroupId !== targetGroupId) {
            this.notification.add(
                'Không thể di chuyển token sang phòng khác. Vui lòng sử dụng chức năng điều phối.',
                { type: 'warning' }
            );
            return false;
        }
        return true;
    }

    /**
     * Get token data from backend
     */
    async _getTokenData(recordId) {
        const token = await this.orm.read('mate.queue.token', [recordId], ['position', 'state', 'room_id']);
        console.log("Token data:", token);

        if (!token || token.length === 0) {
            throw new Error('Token không tồn tại');
        }

        return token[0];
    }

    /**
     * Validate token state
     */
    _validateTokenState(token) {
        if (token.state !== 'waiting') {
            console.log('Token state:', token.state);
            throw new Error('Chỉ có thể di chuyển token đang chờ');
        }
        return true;
    }

    /**
     * Calculate new position based on drop location
     */
    async _calculateNewPosition(recordId, token, previous) {
        const oldPosition = token.position;

        if (!previous) {
            return 1; // Dropped at the beginning
        }

        const prevId = this._getPreviousElementId(previous, recordId);
        if (!prevId) {
            return oldPosition; // Same position
        }

        const prevPosition = await this._getPreviousTokenPosition(prevId);
        return this._determineNewPosition(oldPosition, prevPosition);
    }

    /**
     * Get previous element ID
     */
    _getPreviousElementId(previous, currentRecordId) {
        const prevElement = previous.closest('[data-id]');
        const prevId = prevElement ? parseInt(prevElement.dataset.id) : null;

        console.log('Previous element ID:', prevId);
        return (prevId && prevId !== currentRecordId) ? prevId : null;
    }

    /**
     * Get previous token position
     */
    async _getPreviousTokenPosition(prevId) {
        const prevTokenData = await this.orm.read('mate.queue.token', [prevId], ['position']);
        return prevTokenData && prevTokenData.length > 0 ? prevTokenData[0].position : null;
    }

    /**
     * Determine new position based on movement direction
     */
    _determineNewPosition(oldPosition, prevPosition) {
        if (!prevPosition) return oldPosition;

        return oldPosition < prevPosition ? prevPosition : prevPosition + 1;
    }

    /**
     * Perform the reorder operation
     */
    async _performReorder(recordId, token, newPosition) {
        const oldPosition = token.position;

        console.log(`Moving token ${recordId} from position ${oldPosition} to ${newPosition}`);

        if (oldPosition === newPosition) {
            console.log('Position unchanged, skipping');
            return;
        }

        const result = await this.orm.call(
            'mate.queue.token',
            'reorder_position',
            [recordId, newPosition, oldPosition]
        );

        if (result) {
            this.notification.add(
                `Token đã được di chuyển từ vị trí ${oldPosition} đến vị trí ${newPosition}`,
                { type: 'success' }
            );
            await this._reloadView();
        }
    }

    /**
     * Handle errors and reload view
     */
    async _handleError(error) {
        console.error('Error in sortRecordDrop:', error);
        this.notification.add(
            error.message || 'Không thể di chuyển token',
            { type: 'danger' }
        );
        await this._reloadView();
    }

    /**
     * Reload view and maintain layout
     */
    async _reloadView() {
        await this.props.list.model.load();
        this.ensureSingleColumnLayout();
    }

    /**
     * Override to ensure records can be resequenced
     */
    get canResequenceRecords() {
        return true;
    }

    /**
     * Override to ensure records can be moved
     */
    get canMoveRecords() {
        return false; // Disable moving between groups
    }
}

// Register the custom kanban view
export const queueCoordinationKanbanView = {
    ...kanbanView,
    Renderer: QueueCoordinationKanbanRenderer,
};

registry.category("views").add("queue_coordination_kanban", queueCoordinationKanbanView);