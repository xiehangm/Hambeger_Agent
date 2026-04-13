"""
test_recipes.py — 配方系统 & 层结构约束 自动化测试
测试 match_recipe() 和 validate_structure() 的所有边界情况
"""

from hamburger.recipes import match_recipe, validate_structure, RECIPES

# ANSI 颜色
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0


def check(test_name: str, actual, expected, detail: str = ""):
    global passed, failed
    ok = actual == expected
    icon = f"{GREEN}✅ PASS{RESET}" if ok else f"{RED}❌ FAIL{RESET}"
    print(f"  {icon}  {test_name}")
    if not ok:
        print(f"         期望: {expected}")
        print(f"         实际: {actual}")
        if detail:
            print(f"         说明: {detail}")
        failed += 1
    else:
        passed += 1


# ============================================================
#  一、validate_structure() — 层结构约束测试
# ============================================================
print(f"\n{BOLD}{CYAN}{'='*60}")
print("  一、结构验证 validate_structure() 测试")
print(f"{'='*60}{RESET}\n")

# 1.1 空画布
res = validate_structure([])
check("空画布 → 报错", res["valid"], False)

# 1.2 顶部面包不在第一位
res = validate_structure(["meat_patty", "top_bread", "bottom_bread"])
check("顶部面包不在最上方 → 报错", res["valid"], False)
check("错误信息包含'顶部面包'", "顶部面包" in res.get("error", ""), True)

# 1.3 底部面包不在最后位
res = validate_structure(["top_bread", "bottom_bread", "meat_patty"])
check("底部面包不在最下方 → 报错", res["valid"], False)
check("错误信息包含'底部面包'", "底部面包" in res.get("error", ""), True)

# 1.4 缺少肉饼
res = validate_structure(["top_bread", "cheese", "bottom_bread"])
check("缺少肉饼 → 报错", res["valid"], False)
check("错误信息包含'肉饼'", "肉饼" in res.get("error", ""), True)

# 1.5 最小合法结构（basic_chat 结构）
res = validate_structure(["top_bread", "meat_patty", "bottom_bread"])
check("最小合法结构 [top, meat, bottom] → 通过", res["valid"], True)

# 1.6 四层合法结构（guided_chat 结构）
res = validate_structure(["top_bread", "cheese", "meat_patty", "bottom_bread"])
check("合法结构 [top, cheese, meat, bottom] → 通过", res["valid"], True)

# 1.7 五层合法结构（tool_agent 结构）
res = validate_structure(["top_bread", "cheese", "meat_patty", "lettuce", "bottom_bread"])
check("合法结构 [top, cheese, meat, lettuce, bottom] → 通过", res["valid"], True)

# 1.8 只有一个食材
res = validate_structure(["meat_patty"])
check("只有肉饼 → 报错 (缺面包)", res["valid"], False)

# 1.9 只有顶部面包
res = validate_structure(["top_bread"])
check("只有顶部面包 → 报错", res["valid"], False)

# 1.10 两片面包但没有肉饼
res = validate_structure(["top_bread", "bottom_bread"])
check("只有两片面包没有肉饼 → 报错", res["valid"], False)

# 1.11 两个顶部面包
res = validate_structure(["top_bread", "meat_patty", "top_bread"])
check("两个顶部面包结尾不是 bottom → 报错", res["valid"], False)

# 1.12 底部面包在中间
res = validate_structure(["top_bread", "bottom_bread", "meat_patty", "bottom_bread"])
check("中间有 bottom_bread 但末尾也是 bottom → 通过", res["valid"], True,
      "validate_structure 只检查首尾，不检查中间重复")


# ============================================================
#  二、match_recipe() — 配方匹配测试
# ============================================================
print(f"\n{BOLD}{CYAN}{'='*60}")
print("  二、配方匹配 match_recipe() 测试")
print(f"{'='*60}{RESET}\n")

# 2.1 basic_chat: top_bread + meat_patty + bottom_bread (无 cheese, 无 lettuce)
recipe = match_recipe(["top_bread", "meat_patty", "bottom_bread"])
check("basic_chat 匹配", recipe["name"] if recipe else None, "basic_chat")

# 2.2 guided_chat: top_bread + cheese + meat_patty + bottom_bread (无 lettuce)
recipe = match_recipe(["top_bread", "cheese", "meat_patty", "bottom_bread"])
check("guided_chat 匹配", recipe["name"] if recipe else None, "guided_chat")

# 2.3 tool_agent: top_bread + cheese + meat_patty + lettuce + bottom_bread
recipe = match_recipe(["top_bread", "cheese", "meat_patty", "lettuce", "bottom_bread"])
check("tool_agent 匹配", recipe["name"] if recipe else None, "tool_agent")

# 2.4 顺序无关 — 打乱顺序的 tool_agent
recipe = match_recipe(["bottom_bread", "lettuce", "top_bread", "meat_patty", "cheese"])
check("tool_agent 顺序无关", recipe["name"] if recipe else None, "tool_agent",
      "match_recipe 用 set 匹配，不关心顺序")

# 2.5 有 cheese 有 lettuce → 应匹配 tool_agent（优先级最高）
recipe = match_recipe(["top_bread", "cheese", "lettuce", "meat_patty", "bottom_bread"])
check("cheese+lettuce 优先匹配 tool_agent", recipe["name"] if recipe else None, "tool_agent")

# 2.6 有 cheese 无 lettuce → guided_chat
recipe = match_recipe(["top_bread", "cheese", "meat_patty", "bottom_bread"])
check("有 cheese 无 lettuce → guided_chat", recipe["name"] if recipe else None, "guided_chat")

# 2.7 有 lettuce 无 cheese → 不匹配任何配方
# - tool_agent 需要 cheese ✗
# - guided_chat 需要 cheese ✗
# - basic_chat 禁止 lettuce ✗
recipe = match_recipe(["top_bread", "meat_patty", "lettuce", "bottom_bread"])
check("有 lettuce 无 cheese → default_tool_agent",
      recipe["name"] if recipe else None, "default_tool_agent",
      "肉饼+生菜(无芝士)走默认工具调用配方")

# 2.8 只有 top_bread → 缺少其他必要食材
recipe = match_recipe(["top_bread"])
check("只有 top_bread → 无匹配", recipe, None)

# 2.9 空列表
recipe = match_recipe([])
check("空列表 → 无匹配", recipe, None)

# 2.10 包含多余/自定义食材但满足 tool_agent 条件
recipe = match_recipe(["top_bread", "cheese", "meat_patty", "lettuce", "bottom_bread", "ketchup"])
check("额外食材 'ketchup' 但满足 tool_agent → 匹配",
      recipe["name"] if recipe else None, "tool_agent",
      "tool_agent 无 forbidden 限制，额外食材不影响匹配")

# 2.11 包含额外食材但 basic_chat 被 forbidden 规则阻止
recipe = match_recipe(["top_bread", "meat_patty", "cheese", "bottom_bread"])
check("basic_chat 被 cheese(forbidden) 阻止 → guided_chat",
      recipe["name"] if recipe else None, "guided_chat")

# 2.12 重复食材
recipe = match_recipe(["top_bread", "meat_patty", "meat_patty", "bottom_bread"])
check("重复 meat_patty → 仍匹配 basic_chat",
      recipe["name"] if recipe else None, "basic_chat",
      "set 去重后仍满足 basic_chat 条件")


# ============================================================
#  三、配方注册表一致性检查
# ============================================================
print(f"\n{BOLD}{CYAN}{'='*60}")
print("  三、配方注册表一致性检查")
print(f"{'='*60}{RESET}\n")

# 3.1 检查三个配方存在
check("配方表包含四个配方", len(RECIPES), 4)

# 3.2 配方名称列表
names = [r["name"] for r in RECIPES]
check("配方名称列表正确", names, ["tool_agent", "default_tool_agent", "guided_chat", "basic_chat"])

# 3.3 优先级从高到低: tool_agent > guided_chat > basic_chat
# 也就是说 tool_agent 的 required_set 应该是 guided_chat 的超集
tool_req = set(RECIPES[0]["required_set"])
default_tool_req = set(RECIPES[1]["required_set"])
guided_req = set(RECIPES[2]["required_set"])
basic_req = set(RECIPES[3]["required_set"])
check("tool_agent required ⊃ default_tool_agent required",
      default_tool_req.issubset(tool_req), True)
check("tool_agent required ⊃ guided_chat required",
      guided_req.issubset(tool_req), True)
check("guided_chat required ⊃ basic_chat required",
      basic_req.issubset(guided_req), True)

# 3.4 每个配方都有必要字段
for r in RECIPES:
    has_fields = all(k in r for k in ["name", "label", "description", "emoji", "required_set", "forbidden"])
    check(f"配方 {r['name']} 包含所有必要字段", has_fields, True)

# 3.5 检查所有 required_set 都包含上下面包和肉饼
for r in RECIPES:
    has_bread_and_meat = all(
        item in r["required_set"]
        for item in ["top_bread", "bottom_bread", "meat_patty"]
    )
    check(f"配方 {r['name']} 必须包含上下面包和肉饼", has_bread_and_meat, True)


# ============================================================
#  四、前后端一致性验证
# ============================================================
print(f"\n{BOLD}{CYAN}{'='*60}")
print("  四、前后端配方一致性验证 (逻辑层面)")
print(f"{'='*60}{RESET}\n")

# 验证后端配方和前端配方结构上应保持一致
# 这里只验证后端，前端 JS 逻辑相同但由 recipes.js 实现
# 我们检查后端的已知用例

# 4.1 server.py 中 build_burger 使用 agent_type 分支判断
# agent_type in ("guided_chat", "tool_agent") → 添加 cheese
# agent_type == "tool_agent" and selected_tools → 添加 vegetable
# 验证这与配方定义一致
check("tool_agent 需要 cheese (在 required_set 里)",
      "cheese" in RECIPES[0]["required_set"], True)
check("tool_agent 需要 lettuce (在 required_set 里)",
      "lettuce" in RECIPES[0]["required_set"], True)
check("default_tool_agent 需要 lettuce (在 required_set 里)",
      "lettuce" in RECIPES[1]["required_set"], True)
check("default_tool_agent 禁止 cheese",
      "cheese" in RECIPES[1]["forbidden"], True)
check("guided_chat 需要 cheese (在 required_set 里)",
      "cheese" in RECIPES[2]["required_set"], True)
check("basic_chat 禁止 cheese",
      "cheese" in RECIPES[3]["forbidden"], True)
check("basic_chat 禁止 lettuce",
      "lettuce" in RECIPES[3]["forbidden"], True)


# ============================================================
#  汇总
# ============================================================
print(f"\n{BOLD}{'='*60}")
total = passed + failed
if failed == 0:
    print(f"  {GREEN}🎉 全部通过！{passed}/{total} 测试用例{RESET}")
else:
    print(f"  {RED}⚠️  {failed}/{total} 测试失败{RESET}, {GREEN}{passed} 通过{RESET}")
print(f"{'='*60}{RESET}\n")
