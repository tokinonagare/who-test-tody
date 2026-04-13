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
        "/assign <人数> - 随机抽取指定人数进行测试\n"
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
        untested = db.get_untested()
        # 排除本次已经选过的人，确保结果唯一性
        selectable = [n for n in untested if n not in assigned_this_time]
        
        if not selectable:
            # 如果当前轮次没有可选人员了
            # 可能是所有人都在数据库中标记为已测，或者本次 assign 已经把所有标记为未测的人选完了
            db.reset_all_status()
            await update.message.reply_text("🔁 所有人均已被分配过，触发全员重置机制！")
            
            # 重置后，所有人都是未测。再次过滤掉本次 assign 已经选过的人
            selectable = [n for n in all_names if n not in assigned_this_time]
            
            # 如果还是没有可选的（说明 count > 总池子人数），则允许重复
            if not selectable:
                selectable = all_names
            
        available = len(selectable)
        to_pick_now = min(needed, available)
        
        chosen = random.sample(selectable, to_pick_now)
        # 标记抽出的人为已测
        db.set_tested_status(chosen, 1)
        
        assigned_this_time.extend(chosen)
        needed -= to_pick_now

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
    app.add_handler(CommandHandler("assign", assign))
    app.add_handler(CommandHandler("set", set_status))
    
    logging.info("Bot 正在运行...")
    app.run_polling()

if __name__ == '__main__':
    main()