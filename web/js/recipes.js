/**
 * recipes.js — 前端配方注册表
 * 与后端 hamburger/recipes.py 保持同步
 * 用于前端实时匹配当前画布食材对应的 Agent 类型
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    // =========================================================
    //  配方注册表（优先级由高到低）
    // =========================================================
    const RECIPES = [
        {
            name: 'tool_agent',
            label: '工具调用 Agent',
            description: '挂载了外部工具的智能 Agent，能自主决定调用哪个工具来完成任务',
            emoji: '🤖',
            requiredSet: ['top_bread', 'cheese', 'meat_patty', 'lettuce', 'bottom_bread'],
            forbidden: [],
        },
        {
            name: 'guided_chat',
            label: '场景引导对话',
            description: '通过芝士层注入系统提示词，针对特定场景提供专业引导式回答',
            emoji: '🎯',
            requiredSet: ['top_bread', 'cheese', 'meat_patty', 'bottom_bread'],
            forbidden: ['lettuce'],
        },
        {
            name: 'basic_chat',
            label: '传统 LLM 对话',
            description: '最基础的 LLM 聊天助手，直接与大语言模型交流',
            emoji: '💬',
            requiredSet: ['top_bread', 'meat_patty', 'bottom_bread'],
            forbidden: ['cheese', 'lettuce'],
        },
    ];

    // =========================================================
    //  配方匹配
    // =========================================================
    /**
     * 根据当前画布的食材类型列表匹配配方
     * @param {string[]} layerTypes - 食材 ID 数组，顺序与画布一致
     * @returns {Object|null} 匹配的配方对象，或 null
     */
    function matchRecipe(layerTypes) {
        const typeSet = new Set(layerTypes);

        for (const recipe of RECIPES) {
            const required = new Set(recipe.requiredSet);
            const forbidden = new Set(recipe.forbidden || []);

            // 必须包含所有 required
            let hasAll = true;
            for (const r of required) {
                if (!typeSet.has(r)) { hasAll = false; break; }
            }
            if (!hasAll) continue;

            // 不能包含任何 forbidden
            let hasForbidden = false;
            for (const f of forbidden) {
                if (typeSet.has(f)) { hasForbidden = true; break; }
            }
            if (hasForbidden) continue;

            return recipe;
        }

        return null;
    }

    // =========================================================
    //  汉堡结构验证
    // =========================================================
    /**
     * 验证汉堡层次结构的合法性
     * @param {string[]} layerTypes - 食材 ID 数组（从顶部到底部）
     * @returns {{ valid: boolean, error?: string }}
     */
    function validateStructure(layerTypes) {
        if (!layerTypes || layerTypes.length === 0) {
            return { valid: false, error: '画布上还没有任何食材，请先添加食材！' };
        }

        if (layerTypes[0] !== 'top_bread') {
            return { valid: false, error: '❌ 顶部面包必须在最上方！请将顶部面包移到第一层。' };
        }

        if (layerTypes[layerTypes.length - 1] !== 'bottom_bread') {
            return { valid: false, error: '❌ 底部面包必须在最下方！请将底部面包移到最后一层。' };
        }

        if (!layerTypes.includes('meat_patty')) {
            return { valid: false, error: '❌ 汉堡不能没有肉饼！请添加一个肉饼（LLM）层。' };
        }

        return { valid: true };
    }

    // =========================================================
    //  获取所有配方（供显示指南用）
    // =========================================================
    function getAllRecipes() {
        return RECIPES.slice();
    }

    // 导出
    BurgerGame.Recipes = {
        matchRecipe: matchRecipe,
        validateStructure: validateStructure,
        getAllRecipes: getAllRecipes,
    };
})();
