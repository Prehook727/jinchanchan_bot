'''
金铲铲机器人（集成SQLite数据库）
依赖：
- sqlite3（Python内置，无需安装）
- urllib3==2.6.2
- ChatGPT_HKBU
'''
import sqlite3
import datetime
import logging
import time
from ChatGPT_HKBU import ChatGPT
import configparser

# 全局变量
gpt = None
DB_PATH = "jinchanchan.db"  # SQLite数据库文件路径

# 配置日志
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# LLM优化Prompt模板（基于数据库查询结果）
LLM_OPTIMIZE_TEMPLATE = """
请将以下基础阵容数据优化为金铲铲玩家易读的结构化推荐（适配{S16}版本）：
海克斯：{hextech_name}
基础阵容信息：
- 阵容名称：{team_name}
- 主C：{core_c}，主坦：{core_tank}
- 阵容组成：{composition}
- 核心出装：{equipment}
- 运营思路：{operation}

优化要求：
1. 按「核心阵容、核心装备、运营思路、适配补充」分模块
2. 语言简洁，符合手游玩家阅读习惯
3. 补充该海克斯的适配补充（可替换海克斯、克制关系）
"""

# -------------------------- 数据库操作函数 --------------------------
def init_database():
    """初始化数据库：创建表+插入基础测试数据"""
    conn = None
    try:
        # 连接数据库（不存在则自动创建）
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. 创建海克斯表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS hextech (
            hextech_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hextech_name VARCHAR(50) UNIQUE NOT NULL,
            version VARCHAR(10) NOT NULL,
            description TEXT
        )
        ''')

        # 2. 创建阵容表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS team (
            team_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name VARCHAR(50) UNIQUE NOT NULL,
            core_c VARCHAR(20) NOT NULL,
            core_tank VARCHAR(20) NOT NULL,
            composition TEXT NOT NULL,
            equipment TEXT NOT NULL,
            operation TEXT NOT NULL
        )
        ''')

        # 3. 创建海克斯-阵容关联表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS hextech_team (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hextech_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            FOREIGN KEY (hextech_id) REFERENCES hextech(hextech_id),
            FOREIGN KEY (team_id) REFERENCES team(team_id)
        )
        ''')

        # 4. 创建用户日志表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(50) NOT NULL,
            hextech_name VARCHAR(50) NOT NULL,
            team_name VARCHAR(50) NOT NULL,
            query_time DATETIME NOT NULL,
            response TEXT
        )
        ''')

        # 插入基础测试数据（仅首次运行插入）
        # 插入海克斯
        cursor.execute("INSERT OR IGNORE INTO hextech (hextech_name, version, description) VALUES (?, ?, ?)",
                      ("潘多拉的备战席", "S16", ""))
        cursor.execute("INSERT OR IGNORE INTO hextech (hextech_name, version, description) VALUES (?, ?, ?)",
                      ("珠光莲花", "S13", "技能可以暴击，法强转化为暴击伤害，适合法爆流阵容"))

        # 插入阵容
        cursor.execute("INSERT OR IGNORE INTO team (team_name, core_c, core_tank, composition, equipment, operation) VALUES (?, ?, ?, ?, ?, ?)",
                      (
                          "法师瑞兹",
                          "瑞兹",
                          "蕾欧娜",
                          "瑞兹、蕾欧娜、卡莎、艾克、迦娜、奥利安娜、维克托（7人口成型）",
                          "瑞兹：蓝buff+法爆+大天使；蕾欧娜：狂徒+反甲+龙牙；多余装备给卡莎",
                          "前期用约德尔人+法师打工，6人口小D找2星瑞兹，7人口成型，8人口补维克托开高法强"
                      ))
        cursor.execute("INSERT OR IGNORE INTO team (team_name, core_c, core_tank, composition, equipment, operation) VALUES (?, ?, ?, ?, ?, ?)",
                      (
                          "法爆流拉克丝",
                          "拉克丝",
                          "石头人",
                          "拉克丝、石头人、安妮、狐狸、佐伊、维迦（6人口成型）",
                          "拉克丝：法爆+帽子+法穿棒；石头人：日炎+反甲+狂徒；多余装备给狐狸",
                          "前期走连败拿法强装备，5人口D出2星拉克丝，6人口开6法，7人口补维迦提升上限"
                      ))

        # 建立关联关系
        cursor.execute("INSERT OR IGNORE INTO hextech_team (hextech_id, team_id, priority) VALUES ((SELECT hextech_id FROM hextech WHERE hextech_name='蓝电池'), (SELECT team_id FROM team WHERE team_name='法师瑞兹'), 1)")
        cursor.execute("INSERT OR IGNORE INTO hextech_team (hextech_id, team_id, priority) VALUES ((SELECT hextech_id FROM hextech WHERE hextech_name='珠光莲花'), (SELECT team_id FROM team WHERE team_name='法爆流拉克丝'), 1)")

        conn.commit()
        logger.info("数据库初始化成功，已创建表并插入基础测试数据")

    except sqlite3.Error as e:
        logger.error(f"数据库初始化失败：{e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def query_team_by_hextech(hextech_name):
    """根据海克斯名称查询适配的阵容（优先最高优先级）"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 联表查询：海克斯→关联表→阵容表
        cursor.execute('''
        SELECT t.team_name, t.core_c, t.core_tank, t.composition, t.equipment, t.operation
        FROM hextech h
        JOIN hextech_team ht ON h.hextech_id = ht.hextech_id
        JOIN team t ON ht.team_id = t.team_id
        WHERE h.hextech_name = ?
        ORDER BY ht.priority ASC
        LIMIT 1
        ''', (hextech_name,))

        result = cursor.fetchone()
        if not result:
            logger.warning(f"未查询到[{hextech_name}]对应的阵容数据")
            return None

        # 封装结果为字典
        team_data = {
            "team_name": result[0],
            "core_c": result[1],
            "core_tank": result[2],
            "composition": result[3],
            "equipment": result[4],
            "operation": result[5]
        }
        return team_data

    except sqlite3.Error as e:
        logger.error(f"查询阵容失败：{e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def insert_user_log(user_id, hextech_name, team_name, response):
    """插入用户交互日志"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO user_log (user_id, hextech_name, team_name, query_time, response)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, hextech_name, team_name, datetime.datetime.now(), response))
        conn.commit()
        logger.info(f"用户[{user_id}]的交互日志已记录")
    except sqlite3.Error as e:
        logger.error(f"插入日志失败：{e}", exc_info=True)
    finally:
        if conn:
            conn.close()

# -------------------------- ChatGPT初始化 --------------------------
def init_gpt():
    """初始化ChatGPT"""
    global gpt
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    gpt = ChatGPT(config)
    logger.info("ChatGPT初始化成功")

# -------------------------- 核心交互逻辑 --------------------------
def local_chat_test():
    """本地测试：数据库查询 + LLM优化 + 日志记录"""
    print("="*60)
    print("🎮 金铲铲机器人（集成数据库版）")
    print("💡 输入海克斯名称（如：蓝电池），输入'exit'退出")
    print("="*60)

    # 固定本地测试用户ID
    local_user_id = "local_test_user_001"

    while True:
        user_hextech = input("\n请输入你选择的海克斯强化：").strip()

        # 退出逻辑
        if user_hextech.lower() in ['exit', 'quit', '退出']:
            print("👋 测试结束，再见！")
            break
        if not user_hextech:
            print("⚠️ 请输入有效的海克斯名称！")
            continue

        print("🤔 正在查询最优阵容...", end='', flush=True)

        # 步骤1：查询数据库获取基础阵容数据
        team_data = query_team_by_hextech(user_hextech)
        if not team_data:
            print(f"\r❌ 未找到[{user_hextech}]对应的阵容数据，将调用LLM生成通用推荐...")
            # 降级方案：直接调用LLM生成
            prompt = f"推荐金铲铲S13版本[{user_hextech}]海克斯的适配阵容，按核心阵容、装备、运营思路分模块"
            try:
                response = gpt.submit(prompt)
                print(f"\r✅ 阵容推荐生成完成：\n{response}")
                insert_user_log(local_user_id, user_hextech, "通用推荐", response)
            except Exception as e:
                print(f"\r❌ 生成失败：{e}")
            continue

        # 步骤2：调用LLM优化基础数据（结构化+补充信息）
        try:
            start_time = time.time()
            optimize_prompt = LLM_OPTIMIZE_TEMPLATE.format(
                hextech_name=user_hextech,
                **team_data  # 解包阵容数据
            )
            response = gpt.submit(optimize_prompt)
            cost_time = round(time.time() - start_time, 2)

            # 步骤3：输出结果 + 记录日志
            print(f"\r✅ 阵容推荐生成完成（耗时 {cost_time}s）：\n{response}")
            insert_user_log(local_user_id, user_hextech, team_data["team_name"], response)

        except Exception as e:
            print(f"\r❌ LLM优化失败：{e}")
            logger.error(f"LLM优化失败：{e}", exc_info=True)

# -------------------------- 主函数 --------------------------
if __name__ == '__main__':
    try:
        # 初始化数据库（首次运行自动创建表+插入测试数据）
        init_database()
        # 初始化ChatGPT
        init_gpt()
        # 启动本地测试
        local_chat_test()
    except KeyboardInterrupt:
        print("\n⚠️ 程序被手动中断！")
    except Exception as e:
        print(f"\n❌ 程序启动失败：{e}")
        logger.error(f"启动失败：{e}", exc_info=True)