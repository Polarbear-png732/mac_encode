import os
import time
import sys

# --- ANSI 颜色与样式定义 ---
class UI:
    # 颜色
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    # 清屏
    @staticmethod
    def clear():
        os.system('cls' if os.name == 'nt' else 'clear')

    # 针对 Windows 启用颜色支持
    @staticmethod
    def init():
        if os.name == 'nt':
            os.system('color')

class TranscoderCLI:
    def __init__(self):
        # 模拟配置数据
        self.config = [
            {"id": "1", "name": "普通(需备案)", "path": "--", "ready": False},
            {"id": "2", "name": "普通(不需备案)", "path": "--", "ready": False},
            {"id": "3", "name": "江苏(需备案)", "path": "--", "ready": False},
            {"id": "4", "name": "江苏(不需备案)", "path": "--", "ready": False},
        ]
        self.stats = {"total": 12, "success": 10, "skip": 1, "fail": 1, "time": "152s"}

    def draw_header(self):
        """1. 启动与配置摘要界面"""
        print(f"\n{UI.CYAN}╭──────────────────────────────────────────────────────────────╮")
        print(f"│                🚀 {UI.BOLD}视频转码自动化工具  v1.0.0{UI.RESET}{UI.CYAN}                 │")
        print(f"╰──────────────────────────────────────────────────────────────╯{UI.RESET}")
        
        print(f"\n 📂 {UI.BOLD}当前配置状态:{UI.RESET}")
        print(f" {UI.GRAY}--------------------------------------------------------------{UI.RESET}")
        print(f"  {'场景类型':<20} {'状态':<10} {'目录路径'}")
        print(f" {UI.GRAY}--------------------------------------------------------------{UI.RESET}")
        
        for item in self.config:
            status = f"{UI.RED}[未配置]{UI.RESET}" if not item['ready'] else f"{UI.GREEN}[已就绪]{UI.RESET}"
            print(f"  {item['id']}. {item['name']:<16} {status:<18} {UI.GRAY}{item['path']}{UI.RESET}")
        
        print(f" {UI.GRAY}--------------------------------------------------------------{UI.RESET}")
        print(f" {UI.YELLOW}⚠️  警告: 尚未配置有效路径，请先执行 [6] 修改目录配置。{UI.RESET}")
        print(f"\n {UI.GRAY}[Enter] 进入交互菜单 | [Exit] 退出程序 | [Ctrl+C] 中断任务{UI.RESET}")

    def draw_main_menu(self):
        """2. 交互主菜单"""
        print(f"\n {UI.BOLD}🛠️  请选择操作模式:{UI.RESET}\n")
        # 分栏显示
        menu_items = [
            (f"{UI.BLUE}[1] 🔹 普通(需备案号){UI.RESET}", f"{UI.GREEN}[5] 🚀 全部处理 (已配置){UI.RESET}"),
            (f"{UI.BLUE}[2] 🔹 普通(不需备案){UI.RESET}", f"{UI.CYAN}[6] ⚙️  修改目录配置{UI.RESET}"),
            (f"{UI.BLUE}[3] 🔸 江苏(需备案号){UI.RESET}", f"{UI.CYAN}[7] 📋 查看详细配置{UI.RESET}"),
            (f"{UI.BLUE}[4] 🔸 江苏(不需备案){UI.RESET}", f"{UI.RED}[exit] 退出程序{UI.RESET}"),
        ]
        for left, right in menu_items:
            print(f"  {left:<35} {right}")
        
        return input(f"\n {UI.YELLOW}💡 请输入选项 (1-7):{UI.RESET} ").strip().lower()

    def simulate_processing(self):
        """3. 执行任务时的动态样式"""
        UI.clear()
        print(f"\n 🛰️  {UI.BOLD}正在处理 [普通-需备案号]...{UI.RESET}")
        print(f" {UI.GRAY}--------------------------------------------------------------{UI.RESET}")
        
        # 模拟日志输出
        tasks = [
            (f"{UI.GREEN}🟢 [成功]{UI.RESET}", "video_001.mp4  =>  Transcoding Finished."),
            (f"{UI.YELLOW}🟡 [跳过]{UI.RESET}", "video_002.mp4  =>  已存在同名备案文件."),
            (f"{UI.RED}🔴 [失败]{UI.RESET}", "video_003.mp4  =>  FFmpeg: Permission Denied."),
        ]
        
        for icon, msg in tasks:
            time.sleep(0.5)
            print(f" {icon} {msg}")
            
        # 模拟进度条
        print(f" {UI.GRAY}--------------------------------------------------------------{UI.RESET}")
        progress = 14  # 70%
        bar = "█" * progress + "░" * (20 - progress)
        print(f" 进度: [{UI.GREEN}{bar}{UI.RESET}] 70% | 剩余时间: 00:02:15")
        input(f"\n{UI.GRAY}按回车返回菜单...{UI.RESET}")

    def draw_exit_summary(self):
        """4. 退出汇总界面"""
        s = self.stats
        print(f"\n {UI.BOLD}📊 会话执行汇总{UI.RESET}")
        print(f" {UI.BLUE}┏━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┓{UI.RESET}")
        print(f" {UI.BLUE}┃{UI.RESET} 总扫描   {UI.BLUE}┃{UI.RESET} 成功 {UI.BLUE}┃{UI.RESET} 跳过 {UI.BLUE}┃{UI.RESET} 失败 {UI.BLUE}┃{UI.RESET} 耗时 {UI.BLUE}┃{UI.RESET}")
        print(f" {UI.BLUE}┣━━━━━━━━━━╋━━━━━━╋━━━━━━╋━━━━━━╋━━━━━━┫{UI.RESET}")
        print(f" {UI.BLUE}┃{UI.RESET} {s['total']:<8} {UI.BLUE}┃{UI.RESET} {UI.GREEN}{s['success']:<4}{UI.RESET} {UI.BLUE}┃{UI.RESET} {UI.YELLOW}{s['skip']:<4}{UI.RESET} {UI.BLUE}┃{UI.RESET} {UI.RED}{s['fail']:<4}{UI.RESET} {UI.BLUE}┃{UI.RESET} {s['time']:<4} {UI.BLUE}┃{UI.RESET}")
        print(f" {UI.BLUE}┗━━━━━━━━━━┻━━━━━━┻━━━━━━┻━━━━━━┻━━━━━━┛{UI.RESET}")

    def run(self):
        UI.init()
        try:
            while True:
                UI.clear()
                self.draw_header()
                # 模拟按下回车进入菜单
                input() 
                
                UI.clear()
                self.draw_header() # 保持页眉
                choice = self.draw_main_menu()
                
                if choice == 'exit':
                    UI.clear()
                    self.draw_exit_summary()
                    break
                elif choice in ['1', '2', '3', '4', '5']:
                    self.simulate_processing()
                elif choice == '6':
                    input(f"\n {UI.CYAN}[配置模式] 演示中，按回车返回...{UI.RESET}")
                else:
                    continue
        except KeyboardInterrupt:
            print(f"\n\n{UI.RED} 中断退出...{UI.RESET}")
            sys.exit()

if __name__ == "__main__":
    app = TranscoderCLI()
    app.run()