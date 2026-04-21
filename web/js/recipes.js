/**
 * recipes.js — 前端配方客户端（单一来源：后端 /api/recipes）
 *
 * 不再硬编码配方列表。启动时从后端拉取，缓存到本地供匹配器/UI 使用。
 * 提供：
 *   BurgerGame.Recipes.init()           — 启动时调用一次，返回 Promise
 *   BurgerGame.Recipes.getAllRecipes()  — 同步，拿到缓存的配方列表
 *   BurgerGame.Recipes.matchRecipe(...)
 *   BurgerGame.Recipes.validateStructure(...)
 *   BurgerGame.Recipes.onReady(cb)      — 数据就绪后的回调
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    let RECIPES = [];
    let readyPromise = null;
    const readyCallbacks = [];

    // =========================================================
    //  初始化：从后端拉取配方列表
    // =========================================================
    function init() {
        if (readyPromise) return readyPromise;
        readyPromise = fetch('/api/recipes')
            .then((r) => {
                if (!r.ok) throw new Error('failed to load recipes: ' + r.status);
                return r.json();
            })
            .then((data) => {
                RECIPES = (data.recipes || []).map(normalize);
                readyCallbacks.splice(0).forEach((cb) => {
                    try { cb(RECIPES); } catch (e) { console.error(e); }
                });
                return RECIPES;
            })
            .catch((err) => {
                console.warn('[Recipes] 加载配方失败，使用空列表兜底:', err);
                RECIPES = [];
                return RECIPES;
            });
        return readyPromise;
    }

    function normalize(r) {
        // 后端 recipe_summary 已是声明式数据，这里仅补全驼峰别名方便 JS 使用
        return {
            name: r.name,
            label: r.label,
            description: r.description || '',
            emoji: r.emoji || '🍔',
            requiredSet: r.required_set || [],
            forbidden: r.forbidden || [],
            capabilities: r.capabilities || {},
            canvasLayers: r.canvas_layers || [],
            defaultConfig: r.default_config || {},
            edges: r.edges || [],
            conditional_edges: r.conditional_edges || [],
            nodes: r.nodes || [],
        };
    }

    function onReady(cb) {
        if (!readyPromise) init();
        readyPromise.then(() => cb(RECIPES));
    }

    function getAllRecipes() {
        return RECIPES.slice();
    }

    // =========================================================
    //  配方匹配
    // =========================================================
    function matchRecipe(layerTypes) {
        const typeSet = new Set(layerTypes);
        for (const recipe of RECIPES) {
            const required = new Set(recipe.requiredSet);
            const forbidden = new Set(recipe.forbidden || []);

            let hasAll = true;
            for (const r of required) {
                if (!typeSet.has(r)) { hasAll = false; break; }
            }
            if (!hasAll) continue;

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
    //  结构校验（与后端 validate_structure 对齐）
    // =========================================================
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

    function getRecipe(name) {
        return RECIPES.find((r) => r.name === name) || null;
    }

    // 导出
    BurgerGame.Recipes = {
        init: init,
        onReady: onReady,
        getAllRecipes: getAllRecipes,
        matchRecipe: matchRecipe,
        validateStructure: validateStructure,
        getRecipe: getRecipe,
    };

    // 页面加载时立即开启拉取
    init();
})();
