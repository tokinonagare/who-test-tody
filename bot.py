import os
import random
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import db

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def check_and_reset(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Check if everyone has tested. If so, reset all and notify."""
    testers = db.get_all_testers()
    if not testers:
        return
    
    all_tested = all(has_tested for name, has_tested in testers)
    if all_tested:
        db.reset_all_status()
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎉 所有人均已完成测试！已自动将所有人状态重置为【未测试】。新的一轮开始了！"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "欢迎使用测试人员管理 Bot！\n\n"
        "可用命令：\n"
        "/add <名字> - 添加测试人员\n"
        "/remove <名字> - 删除测试人员\n"
        "/status - 查看当前测试状态\n"
        "/groups - 查看分组名单\n"
        "/setgroup <名字> <1-6> - 设置人员分组\n"
        "/assign <人数> - 随机抽取指定人数进行测试（优先跨组）\n"
        "/set <名字> <1|0> - 手动设置某人的测试状态（1为已测，0为未测）"
    )
    await update.message.reply_text(help_text)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法: /add <名字>")
        return
    name = context.args[0]
    if db.add_tester(name):
        await update.message.reply_text(f"成功添加测试人员: {name}")
    else:
        await update.message.reply_text(f"测试人员 {name} 已存在。")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法: /remove <名字>")
        return
    name = context.args[0]
    if db.remove_tester(name):
        await update.message.reply_text(f"成功移除测试人员: {name}")
    else:
        await update.message.reply_text(f"未找到测试人员: {name}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testers = db.get_all_testers()
    if not testers:
        await update.message.reply_text("当前没有任何测试人员，请使用 /add 添加。")
        return
    
    tested = [name for name, has_tested in testers if has_tested]
    untested = [name for name, has_tested in testers if not has_tested]
    
    msg = "📊 **当前测试状态** 📊\n\n"
    msg += f"✅ **已测试 ({len(tested)})**:\n" + (", ".join(tested) if tested else "无") + "\n\n"
    msg += f"⏳ **未测试 ({len(untested)})**:\n" + (", ".join(untested) if untested else "无")
    
    await update.message.reply_text(msg)

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("用法: /setgroup <名字> <1-6>")
        return
    
    name = context.args[0]
    try:
        group_id = int(context.args[1])
        if not (1 <= group_id <= 6):
            raise ValueError
    except ValueError:
        await update.message.reply_text("组号必须是 1 到 6 之间的整数。")
        return

    if db.set_group(name, group_id):
        await update.message.reply_text(f"成功将 {name} 设置到第 {group_id} 组。")
    else:
        await update.message.reply_text(f"未找到测试人员: {name}")

async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testers = db.get_all_testers_with_group()
    if not testers:
        await update.message.reply_text("当前没有任何测试人员。")
        return
    
    group_map = {i: [] for i in range(7)} # 0 为未分组，1-6 为指定组
    for name, has_tested, group_id in testers:
        status_icon = "✅" if has_tested else "⏳"
        group_map[group_id].append(f"{status_icon} {name}")
    
    msg = "👥 **测试人员分组名单** 👥\n\n"
    for i in range(1, 7):
        members = group_map[i]
        msg += f"📦 **第 {i} 组 ({len(members)}人)**:\n" + (", ".join(members) if members else "空") + "\n\n"
    
    if group_map[0]:
        msg += "❓ **未分组人员**:\n" + ", ".join(group_map[0])
    
    await update.message.reply_text(msg)

async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法: /assign <人数>")
        return
    
    try:
        count = int(context.args[0])
        if count <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("请提供一个有效的正整数作为分配人数。")
        return

    all_testers = db.get_all_testers()
    if not all_testers:
        await update.message.reply_text("当前名单为空，请先使用 /add 添加人员。")
        return

    all_names = [t[0] for t in all_testers]
    assigned_this_time = []
    needed = count

    while needed > 0:
        untested_with_group = db.get_untested_with_group()
        # 排除本次已经选过的人
        selectable_pool = [t for t in untested_with_group if t[0] not in assigned_this_time]
        
        if not selectable_pool:
            db.reset_all_status()
            await update.message.reply_text("🔁 所有人均已被分配过，触发全员重置机制！")
            # 重置后，所有人都是未测。再次过滤掉本次 assign 已经选过的人
            all_testers_with_group = db.get_all_testers_with_group()
            selectable_pool = [t for t in all_testers_with_group if t[0] not in assigned_this_time]
            
            if not selectable_pool:
                # 极端情况：count > 总人数
                selectable_pool = all_testers_with_group
            
        # 按组分类
        group_to_members = {}
        for name, group_id in [(t[0], t[1] if len(t)>1 else 0) for t in selectable_pool]:
            if group_id not in group_to_members:
                group_to_members[group_id] = []
            group_to_members[group_id].append(name)
        
        # 跨组轮询抽取
        groups_list = list(group_to_members.keys())
        random.shuffle(groups_list)
        
        # 只要还需要人，并且还有组可选
        group_exhausted = False
        while needed > 0 and not group_exhausted:
            group_exhausted = True
            # 打乱组顺序，确保公平性
            current_groups = list(groups_list)
            random.shuffle(current_groups)
            
            for g_id in current_groups:
                if needed <= 0: break
                
                members = group_to_members[g_id]
                if members:
                    # 从该组取第一个（最久未测的那个）
                    chosen_one = members[0]
                    assigned_this_time.append(chosen_one)
                    members.remove(chosen_one)
                    db.set_tested_status([chosen_one], 1)
                    needed -= 1
                    group_exhausted = False # 只要这一轮有组还能抽，就没耗尽
                else:
                    if g_id in groups_list:
                        groups_list.remove(g_id)

    await update.message.reply_text(f"🎲 抽取的测试人员 ({count}人): " + ", ".join(assigned_this_time))
    
    # 最后检查一次状态，如果刚才这轮刚好把所有人抽完，自动全员重置并通知
    await check_and_reset(context, update.effective_chat.id)

async def set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("用法: /set <名字> <1|0> (1为已测试，0为未测试)")
        return
    
    name = context.args[0]
    status_str = context.args[1]
    
    if status_str not in ('0', '1'):
        await update.message.reply_text("状态值必须是 1 (已测试) 或 0 (未测试)。")
        return
        
    status_val = int(status_str)
    
    testers_dict = {t[0]: t[1] for t in db.get_all_testers()}
    if name not in testers_dict:
        await update.message.reply_text(f"未找到测试人员: {name}")
        return
        
    db.set_tested_status([name], status_val)
    status_msg = "已测试" if status_val == 1 else "未测试"
    await update.message.reply_text(f"已将 {name} 的状态设置为: {status_msg}")
    
    await check_and_reset(context, update.effective_chat.id)

def main():
    if not TELEGRAM_TOKEN:
        logging.error("请在 .env 文件中设置 TELEGRAM_TOKEN")
        return
        
    db.init_db()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("groups", groups))
    app.add_handler(CommandHandler("setgroup", set_group))
    app.add_handler(CommandHandler("assign", assign))
    app.add_handler(CommandHandler("set", set_status))
    
    logging.info("Bot 正在运行...")
    app.run_polling()

if __name__ == '__main__':
    main()