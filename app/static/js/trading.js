async function toggleChannelForwarding(channelId, isForwarding) {
    try {
        const response = await fetch(`/api/channels/${channelId}/forwarding`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ is_forwarding: isForwarding })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update channel forwarding status');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error toggling channel forwarding:', error);
        throw error;
    }
}

// Channel list item component
Vue.component('channel-list-item', {
    template: '#channel-list-item-template',
    props: {
        channel: Object,
        unreadCount: Number
    },
    methods: {
        selectChannel() {
            this.$emit('select-channel', this.channel);
        },
        async toggleForwarding(event) {
            event.stopPropagation();
            const newValue = !this.channel.is_forwarding;
            try {
                await toggleChannelForwarding(this.channel.platform_channel_id, newValue);
                this.channel.is_forwarding = newValue;
                // 显示成功提示
                this.$notify({
                    title: '成功',
                    message: `已${newValue ? '开启' : '关闭'}转发`,
                    type: 'success',
                    duration: 2000
                });
            } catch (error) {
                console.error('Error toggling channel forwarding:', error);
                // 如果失败，恢复开关状态
                this.channel.is_forwarding = !newValue;
                // 显示错误提示
                this.$notify.error({
                    title: '错误',
                    message: '更新转发状态失败',
                    duration: 2000
                });
            }
        }
    }
}); 