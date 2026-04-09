document.addEventListener('DOMContentLoaded', () => {
    const buildBtn = document.getElementById('build-btn');
    const plate = document.getElementById('plate');
    const loadingOverlay = document.getElementById('loading-overlay');
    
    // Panels
    const visualPanel = document.getElementById('visual-panel');
    const chatPanel = document.getElementById('chat-panel');
    
    // Inputs
    const cheesePrompt = document.getElementById('cheese-prompt');
    const meatModel = document.getElementById('meat-model');
    const toolCalc = document.getElementById('tool-calc');
    const toolWeather = document.getElementById('tool-weather');
    
    // Chat
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const chatBox = document.getElementById('chat-box');

    // Toast
    const toast = document.getElementById('toast');
    
    function showToast(msg, duration=3000) {
        toast.textContent = msg;
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), duration);
    }
    
    // 搭建汉堡动画
    async function animateBuildingBurger(hasCheese, hasVeg) {
        plate.innerHTML = '<div class="plate-base">🍽️</div>'; // clear
        
        const layers = [];
        layers.push({ cls: 'layer-bottom-bread', text: '底层面包' });
        
        if (hasVeg) layers.push({ cls: 'layer-veg', text: '蔬菜 (Tools)' });
        layers.push({ cls: 'layer-meat', text: '肉饼 (LLM)' });
        if (hasCheese) layers.push({ cls: 'layer-cheese', text: '芝士 (Prompt)' });
        
        layers.push({ cls: 'layer-top-bread', text: '顶层面包' });

        for (let i = 0; i < layers.length; i++) {
            const div = document.createElement('div');
            div.className = `burger-layer ${layers[i].cls}`;
            div.textContent = layers[i].text;
            plate.appendChild(div);
            // 简单的延时堆叠效果
            await new Promise(r => setTimeout(r, 400));
        }
    }

    buildBtn.addEventListener('click', async () => {
        const config = {
            cheese_prompt: cheesePrompt.value.trim() || undefined,
            meat_model: meatModel.value,
            vegetables: []
        };
        if (toolCalc.checked) config.vegetables.push('calculate_add');
        if (toolWeather.checked) config.vegetables.push('get_weather');

        // Play animation visually first
        await animateBuildingBurger(!!config.cheese_prompt, config.vegetables.length > 0);
        
        // Show loading and call API
        loadingOverlay.classList.remove('hidden');
        
        try {
            const res = await fetch('/api/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const data = await res.json();
            
            if (res.ok) {
                showToast('🍔 汉堡制作完成！');
                setTimeout(() => {
                    // Switch interface
                    chatPanel.classList.remove('hidden');
                    // auto scroll to bottom
                    chatBox.scrollTop = chatBox.scrollHeight;
                }, 1000);
            } else {
                showToast(`❌ 制作失败: ${data.detail || '未知错误'}`);
            }
        } catch (err) {
            showToast('❌ 网络请求失败，请检查服务器是否开启。');
        } finally {
            loadingOverlay.classList.add('hidden');
        }
    });

    // Chat function
    async function sendMessage() {
        const text = chatInput.value.trim();
        if(!text) return;
        
        // Append user msg
        const userDiv = document.createElement('div');
        userDiv.className = 'message user';
        userDiv.textContent = text;
        chatBox.appendChild(userDiv);
        
        chatInput.value = '';
        chatBox.scrollTop = chatBox.scrollHeight;
        
        // Append loading msg
        const agentDiv = document.createElement('div');
        agentDiv.className = 'message agent';
        agentDiv.textContent = '... (思考中/嚼汉堡中)';
        chatBox.appendChild(agentDiv);
        chatBox.scrollTop = chatBox.scrollHeight;

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });
            const data = await res.json();
            
            if (res.ok) {
                agentDiv.textContent = data.reply;
            } else {
                agentDiv.textContent = `❌ ${data.detail || '错误'}`;
                agentDiv.style.color = 'red';
            }
        } catch (err) {
            agentDiv.textContent = '❌ 通讯故障';
        }
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});
