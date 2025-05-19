import customtkinter as ctk
import datetime
import time
import subprocess
import threading
import psutil
import ctypes
import requests
import json
import os
import tempfile
import asyncio
import sys
from CTkListbox import CTkListbox
from tkinter import messagebox
from PIL import ImageGrab
import discord
from discord.ext import commands

# Windows API için gerekli tanımlamalar
kernel32 = ctypes.WinDLL('kernel32')
psapi = ctypes.WinDLL('psapi')

class AutoUpdater:
    def __init__(self):
        self.repo_url = "https://raw.githubusercontent.com/huyukhu/SystemManager/main/"
        self.current_version = self.get_current_version()
        self.executable_path = sys.executable if getattr(sys, 'frozen', False) else __file__
        self.executable_dir = os.path.dirname(self.executable_path)
        
    def get_current_version(self):
        try:
            version_path = os.path.join(self.executable_dir, 'version.txt')
            with open(version_path, "r") as f:
                return f.read().strip()
        except:
            return "1.0"
            
    def check_update(self):
        try:
            response = requests.get(f"{self.repo_url}version.txt")
            latest_version = response.text.strip()
            
            if latest_version > self.current_version:
                return True, latest_version
            return False, None
        except Exception as e:
            print("Güncelleme kontrol hatası:", str(e))
            return False, None
            
    def perform_update(self):
        try:
            files = ["system_manager.py", "version.txt"]
            for file in files:
                response = requests.get(f"{self.repo_url}{file}")
                file_path = os.path.join(self.executable_dir, file)
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
            
            self.restart_program()
        except Exception as e:
            messagebox.showerror("Hata", f"Güncelleme başarısız: {str(e)}")

    def restart_program(self):
        if getattr(sys, 'frozen', False):
            # EXE için özel yeniden başlatma
            batch_script = f"""
            @echo off
            timeout /t 3 /nobreak >nul
            del "{self.executable_path}"
            move "{os.path.join(self.executable_dir, 'system_manager.py')}" "{self.executable_path}"
            start "" "{self.executable_path}"
            del "%~f0"
            """
            
            with tempfile.NamedTemporaryFile(suffix='.bat', delete=False, mode='w') as bat_file:
                bat_file.write(batch_script)
            
            subprocess.Popen(['cmd', '/c', bat_file.name], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            sys.exit()
        else:
            # Normal Python script için
            python = sys.executable
            os.execl(python, python, *sys.argv)

class ShutdownApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.updater = AutoUpdater()
        self.check_for_updates()
        
        self.title("Advanced System Manager 5.0")
        self.geometry("1200x800")
        
        # Yapılandırma ayarları
        self.config_file = os.path.join(os.getenv('PROGRAMDATA'), 'SystemManager', 'config.json')
        self.load_config()
        
        # Sistem değişkenleri
        self.ram_clean_enabled = False
        self.ram_update_running = True
        self.system_processes = [
            'System', 'Registry', 'smss.exe', 'csrss.exe', 'wininit.exe',
            'services.exe', 'lsass.exe', 'svchost.exe', 'dwm.exe', 'taskhostw.exe'
        ]
        self.preprocessed_processes = []
        self.monitored_processes = []
        self.search_job = None
        self.search_lock = threading.Lock()
        
        # Discord entegrasyonu
        self.discord_webhook = self.config.get('discord_webhook', '')
        self.bot_token = self.config.get('bot_token', '')
        self.screenshot_delete_time = self.config.get('screenshot_delete_time', '60')
        self.bot = None
        self.bot_thread = None
        
        # Arayüz oluşturma
        self.create_main_interface()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.load_processes()
        self.monitor_ram()
        self.start_process_monitor()

    def check_for_updates(self):
        update_available, latest_version = self.updater.check_update()
        if update_available:
            answer = messagebox.askyesno(
                "Güncelleme Mevcut",
                f"Yeni sürüm ({latest_version}) mevcut! Güncellemek ister misiniz?"
            )
            if answer:
                self.updater.perform_update()

    def create_main_interface(self):
        self.tab_view = ctk.CTkTabview(master=self)
        self.tab_view.pack(fill='both', expand=True, padx=20, pady=20)
        
        tabs = [
            ("⏻ Sistem Kapatma", self.create_shutdown_content),
            ("⏱ Geri Sayım", self.create_countdown_content),
            ("💾 RAM Yönetimi", self.create_ram_content),
            ("✖ Program Kapatma", self.create_process_content),
            ("🔔 Bildirimler", self.create_discord_content),
            ("🤖 Discord Bot2", self.create_bot_content),
            ("🔄 Güncellemeler", self.create_update_content)
        ]
        
        for tab_name, tab_method in tabs:
            tab = self.tab_view.add(tab_name)
            tab_method(tab)

    def create_update_content(self, tab):
        frame = ctk.CTkFrame(master=tab)
        frame.pack(pady=20, padx=20, fill='both', expand=True)
        
        ctk.CTkLabel(frame, text="Otomatik Güncelleme Ayarları", font=("Arial", 16)).pack(pady=10)
        
        info_frame = ctk.CTkFrame(frame)
        info_frame.pack(pady=10)
        
        ctk.CTkLabel(info_frame, text="Mevcut Versiyon:").pack(side='left', padx=5)
        self.version_label = ctk.CTkLabel(info_frame, text=self.updater.current_version)
        self.version_label.pack(side='left', padx=5)
        
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(pady=10)
        ctk.CTkButton(
            btn_frame, 
            text="Şimdi Kontrol Et", 
            command=lambda: self.check_for_updates(),
            fg_color="#5bc0de"
        ).pack(side='left', padx=5)

    def create_shutdown_content(self, tab):
        frame = ctk.CTkFrame(master=tab)
        frame.pack(pady=20, padx=20, fill='both', expand=True)
        
        ctk.CTkLabel(frame, text="Zamanlı Bilgisayar Kapatma", font=("Arial", 16)).pack(pady=10)
        
        time_frame = ctk.CTkFrame(frame)
        time_frame.pack(pady=10)
        
        ctk.CTkLabel(time_frame, text="Saat:").pack(side='left', padx=5)
        self.shutdown_hour = ctk.CTkEntry(time_frame, width=60, placeholder_text="HH")
        self.shutdown_hour.pack(side='left', padx=5)
        
        ctk.CTkLabel(time_frame, text="Dakika:").pack(side='left', padx=5)
        self.shutdown_min = ctk.CTkEntry(time_frame, width=60, placeholder_text="MM")
        self.shutdown_min.pack(side='left', padx=5)
        
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Ayarla", command=self.set_scheduled_shutdown).pack(side='left', padx=5)
        ctk.CTkButton(btn_frame, text="İptal Et", command=self.cancel_shutdown, fg_color="#d9534f").pack(side='left', padx=5)

    def set_scheduled_shutdown(self):
        try:
            hours = int(self.shutdown_hour.get())
            mins = int(self.shutdown_min.get())
            
            if not (0 <= hours < 24 and 0 <= mins < 60):
                raise ValueError("Geçersiz zaman aralığı (00-23 saat, 00-59 dakika)")
                
            now = datetime.datetime.now()
            target_time = now.replace(hour=hours, minute=mins, second=0, microsecond=0)
            
            if target_time < now:
                target_time += datetime.timedelta(days=1)
                
            threading.Thread(
                target=self.schedule_shutdown,
                args=(target_time,),
                daemon=True
            ).start()
            messagebox.showinfo("Başarılı", f"⏰ Bilgisayar {target_time.strftime('%d.%m.%Y %H:%M')} tarihinde kapanacak")
        except Exception as e:
            messagebox.showerror("Hata", f"❌ Geçersiz giriş: {str(e)}")

    def schedule_shutdown(self, target_time):
        while True:
            now = datetime.datetime.now()
            if now >= target_time:
                subprocess.run(["shutdown", "/s", "/t", "0"], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                break
            time.sleep(1)

    def create_countdown_content(self, tab):
        frame = ctk.CTkFrame(master=tab)
        frame.pack(pady=20, padx=20, fill='both', expand=True)
        
        ctk.CTkLabel(frame, text="Geri Sayımlı Kapatma", font=("Arial", 16)).pack(pady=10)
        
        time_frame = ctk.CTkFrame(frame)
        time_frame.pack(pady=10)
        
        ctk.CTkLabel(time_frame, text="Saat:").pack(side='left', padx=5)
        self.countdown_hour = ctk.CTkEntry(time_frame, width=60, placeholder_text="HH")
        self.countdown_hour.pack(side='left', padx=5)
        
        ctk.CTkLabel(time_frame, text="Dakika:").pack(side='left', padx=5)
        self.countdown_min = ctk.CTkEntry(time_frame, width=60, placeholder_text="MM")
        self.countdown_min.pack(side='left', padx=5)
        
        ctk.CTkButton(frame, text="Başlat", command=self.set_countdown_shutdown).pack(pady=10)

    def set_countdown_shutdown(self):
        try:
            hours = int(self.countdown_hour.get())
            mins = int(self.countdown_min.get())
            
            if not (0 <= hours < 24 and 0 <= mins < 60):
                raise ValueError("Geçersiz zaman aralığı (00-23 saat, 00-59 dakika)")
                
            seconds = hours * 3600 + mins * 60
            threading.Thread(
                target=self.countdown_shutdown,
                args=(seconds,),
                daemon=True
            ).start()
            messagebox.showinfo("Başarılı", f"⏳ {hours} saat {mins} dakika sonra kapanacak")
        except Exception as e:
            messagebox.showerror("Hata", f"❌ Geçersiz giriş: {str(e)}")

    def countdown_shutdown(self, seconds):
        time.sleep(seconds)
        subprocess.run(["shutdown", "/s", "/t", "0"], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def cancel_shutdown(self):
        subprocess.run(["shutdown", "/a"], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        messagebox.showinfo("Bilgi", "✅ Tüm kapatma planları iptal edildi")

    def create_ram_content(self, tab):
        frame = ctk.CTkFrame(master=tab)
        frame.pack(pady=20, padx=20, fill='both', expand=True)
        
        ctk.CTkLabel(frame, text="Canlı RAM İzleme", font=("Arial", 16)).pack(pady=10)
        self.ram_usage_label = ctk.CTkLabel(frame, text="RAM Kullanımı: %0")
        self.ram_usage_label.pack()
        self.ram_progress = ctk.CTkProgressBar(frame, height=25, width=300)
        self.ram_progress.set(0)
        self.ram_progress.pack(pady=10)
        
        threshold_frame = ctk.CTkFrame(frame)
        threshold_frame.pack(pady=10)
        ctk.CTkLabel(threshold_frame, text="Otomatik Temizleme Eşiği:").pack(side='left', padx=5)
        self.ram_threshold_entry = ctk.CTkEntry(threshold_frame, width=60)
        self.ram_threshold_entry.pack(side='left', padx=5)
        ctk.CTkLabel(threshold_frame, text="%").pack(side='left', padx=5)
        
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(pady=10)
        self.auto_clean_btn = ctk.CTkButton(btn_frame, text="Otomatik", command=self.toggle_ram_clean)
        self.auto_clean_btn.pack(side='left', padx=5)
        ctk.CTkButton(btn_frame, text="Manuel Temizle", command=self.clean_ram, fg_color="#5cb85c").pack(side='left', padx=5)

    def toggle_ram_clean(self):
        self.ram_clean_enabled = not self.ram_clean_enabled
        self.auto_clean_btn.configure(fg_color=("red" if self.ram_clean_enabled else None))

    def clean_ram(self):
        for proc in psutil.process_iter():
            try:
                handle = kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
                psapi.EmptyWorkingSet(handle)
                kernel32.CloseHandle(handle)
            except:
                continue
        messagebox.showinfo("Başarılı", "RAM başarıyla temizlendi")

    def create_process_content(self, tab):
        frame = ctk.CTkFrame(master=tab)
        frame.pack(pady=20, padx=20, fill='both', expand=True)
        
        toolbar_frame = ctk.CTkFrame(frame)
        toolbar_frame.pack(fill='x', pady=5)
        
        ctk.CTkButton(
            toolbar_frame,
            text="🔄 Listeyi Yenile",
            command=self.load_processes,
            width=100,
            fg_color="#5bc0de"
        ).pack(side='right', padx=5)
        
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            toolbar_frame,
            placeholder_text="Uygulama ara...",
            textvariable=self.search_var,
            width=300
        )
        self.search_entry.pack(side='left', fill='x', expand=True, padx=5)
        self.search_var.trace_add("write", self.schedule_search)
        
        self.process_list = CTkListbox(frame, width=500, height=300)
        self.process_list.pack(pady=10, fill='both', expand=True)
        
        time_frame = ctk.CTkFrame(frame)
        time_frame.pack(pady=10)
        
        self.process_option = ctk.StringVar(value="time")
        option_frame = ctk.CTkFrame(time_frame)
        option_frame.pack(pady=5)
        
        ctk.CTkRadioButton(
            option_frame,
            text="Saat Seçimi",
            variable=self.process_option,
            value="time"
        ).pack(side='left', padx=10)
        
        ctk.CTkRadioButton(
            option_frame,
            text="Geri Sayım",
            variable=self.process_option,
            value="countdown"
        ).pack(side='left', padx=10)
        
        self.time_input_frame = ctk.CTkFrame(time_frame)
        self.time_input_frame.pack(pady=5)
        
        ctk.CTkLabel(self.time_input_frame, text="Saat:").pack(side='left', padx=5)
        self.process_hour = ctk.CTkEntry(self.time_input_frame, width=50, placeholder_text="HH")
        self.process_hour.pack(side='left', padx=5)
        
        ctk.CTkLabel(self.time_input_frame, text="Dakika:").pack(side='left', padx=5)
        self.process_min = ctk.CTkEntry(self.time_input_frame, width=50, placeholder_text="MM")
        self.process_min.pack(side='left', padx=5)
        
        self.countdown_input_frame = ctk.CTkFrame(time_frame)
        self.countdown_input_frame.pack_forget()
        
        ctk.CTkLabel(self.countdown_input_frame, text="Saat:").pack(side='left', padx=5)
        self.countdown_hours = ctk.CTkEntry(self.countdown_input_frame, width=50, placeholder_text="SS")
        self.countdown_hours.pack(side='left', padx=5)
        
        ctk.CTkLabel(self.countdown_input_frame, text="Dakika:").pack(side='left', padx=5)
        self.countdown_mins = ctk.CTkEntry(self.countdown_input_frame, width=50, placeholder_text="DD")
        self.countdown_mins.pack(side='left', padx=5)
        
        def show_inputs():
            if self.process_option.get() == "time":
                self.time_input_frame.pack()
                self.countdown_input_frame.pack_forget()
            else:
                self.time_input_frame.pack_forget()
                self.countdown_input_frame.pack()
                
        self.process_option.trace_add("write", lambda *_: show_inputs())
        show_inputs()
        
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(pady=10)
        ctk.CTkButton(
            btn_frame, 
            text="Kapatmayı Planla", 
            command=self.schedule_process_kill, 
            fg_color="#d9534f"
        ).pack(side='left', padx=5)
        ctk.CTkButton(
            btn_frame, 
            text="İzlemeye Al", 
            command=self.add_process_to_monitor,
            fg_color="#7289DA"
        ).pack(side='left', padx=5)

    def schedule_search(self, *args):
        with self.search_lock:
            if self.search_job:
                self.after_cancel(self.search_job)
            self.search_job = self.after(150, self.threaded_filter)

    def threaded_filter(self):
        threading.Thread(target=self.filter_processes, daemon=True).start()

    def filter_processes(self):
        search_term = self.search_var.get().strip().lower()
        
        if not search_term:
            filtered = [(name, pid) for (name, pid, _) in self.preprocessed_processes]
        else:
            filtered = [
                (name, pid)
                for (name, pid, lower_name) in self.preprocessed_processes
                if search_term in lower_name or search_term in pid
            ]
        
        self.after(0, self.update_process_list, filtered)

    def update_process_list(self, processes):
        self.process_list.delete("all")
        for name, pid in processes:
            self.process_list.insert("end", f"{name} (PID: {pid})")

    def load_processes(self):
        self.process_list.delete("all")
        self.preprocessed_processes = []
        
        processes = list(psutil.process_iter(['pid', 'name', 'username']))
        
        process_data = []
        for proc in processes:
            try:
                name = proc.info['name']
                pid = proc.info['pid']
                username = proc.info['username'] or ""
                
                is_system_process = (
                    name in self.system_processes or
                    'SYSTEM' in username.upper() or
                    'SERVICE' in username.upper()
                )
                
                if not is_system_process:
                    lower_name = name.lower()
                    process_data.append((name, str(pid), lower_name))
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
                continue
        
        self.preprocessed_processes = process_data
        self.update_process_list([(name, pid) for name, pid, _ in process_data])

    def schedule_process_kill(self):
        selected = self.process_list.get()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen bir proses seçin")
            return
            
        process_name = selected.split(' (PID:')[0].strip()
        
        try:
            option = self.process_option.get()
            
            if option == "time":
                if not self.process_hour.get() or not self.process_min.get():
                    raise ValueError("Lütfen saat ve dakika girin")
                    
                hours = int(self.process_hour.get())
                mins = int(self.process_min.get())
                
                if not (0 <= hours < 24 and 0 <= mins < 60):
                    raise ValueError("Geçersiz zaman aralığı (00-23 saat, 00-59 dakika)")
                    
                target_time = datetime.datetime.now().replace(hour=hours, minute=mins, second=0, microsecond=0)
                if target_time < datetime.datetime.now():
                    target_time += datetime.timedelta(days=1)
                    
                threading.Thread(
                    target=self.schedule_process_shutdown,
                    args=(process_name, target_time),
                    daemon=True
                ).start()
                messagebox.showinfo("Başarılı", f"⏰ {process_name} {target_time.strftime('%d.%m.%Y %H:%M')} tarihinde kapatılacak")
            
            elif option == "countdown":
                if not self.countdown_hours.get() and not self.countdown_mins.get():
                    raise ValueError("Lütfen saat veya dakika girin")
                
                hours = int(self.countdown_hours.get()) if self.countdown_hours.get() else 0
                mins = int(self.countdown_mins.get()) if self.countdown_mins.get() else 0
                
                if hours < 0 or mins < 0:
                    raise ValueError("Saat ve dakika negatif olamaz")
                if hours == 0 and mins == 0:
                    raise ValueError("Toplam süre 0 olamaz")
                
                total_seconds = (hours * 3600) + (mins * 60)
                threading.Thread(
                    target=self.countdown_process_shutdown,
                    args=(process_name, total_seconds),
                    daemon=True
                ).start()
                messagebox.showinfo("Başarılı", f"⏳ {process_name} {hours} saat {mins} dakika sonra kapatılacak")
                
        except Exception as e:
            messagebox.showerror("Hata", f"❌ Geçersiz giriş: {str(e)}")

    def schedule_process_shutdown(self, process_name, target_time):
        while True:
            now = datetime.datetime.now()
            if now >= target_time:
                self.kill_process(process_name)
                break
            time.sleep(1)

    def countdown_process_shutdown(self, process_name, seconds):
        time.sleep(seconds)
        self.kill_process(process_name)

    def kill_process(self, process_name):
        for proc in psutil.process_iter(['name', 'pid']):
            if proc.info['name'] == process_name:
                try:
                    proc.terminate()
                    return True
                except psutil.AccessDenied:
                    messagebox.showerror("Hata", "Yönetici izni gerekiyor!")
                except psutil.NoSuchProcess:
                    pass
        return False

    def create_discord_content(self, tab):
        frame = ctk.CTkFrame(master=tab)
        frame.pack(pady=20, padx=20, fill='both', expand=True)

        ctk.CTkLabel(frame, text="Discord Bildirim Ayarları", font=("Arial", 16)).pack(pady=10)
        
        webhook_frame = ctk.CTkFrame(frame)
        webhook_frame.pack(pady=10, fill='x', padx=50)
        
        ctk.CTkLabel(webhook_frame, text="Webhook URL:").pack(side='left')
        self.discord_webhook_entry = ctk.CTkEntry(
            webhook_frame, 
            width=400,
            placeholder_text="https://discord.com/api/webhooks/..."
        )
        self.discord_webhook_entry.pack(side='left', fill='x', expand=True)
        self.discord_webhook_entry.insert(0, self.discord_webhook)
        
        ctk.CTkButton(
            frame, 
            text="Ayarları Kaydet", 
            command=self.save_discord_settings,
            fg_color="#5865F2"
        ).pack(pady=10)

        ctk.CTkButton(
            frame, 
            text="Bildirim Testi Gönder", 
            command=self.send_test_notification,
            fg_color="#57F287"
        ).pack(pady=5)

    def save_discord_settings(self):
        self.discord_webhook = self.discord_webhook_entry.get().strip()
        self.save_config()
        messagebox.showinfo("Başarılı", "Discord ayarları kaydedildi!")

    def send_test_notification(self):
        if not self.discord_webhook:
            messagebox.showerror("Hata", "Lütfen önce webhook URL girin!")
            return
            
        try:
            self.send_discord_message("Sistem Yöneticisi", "✅ Bildirim testi başarılı!")
            messagebox.showinfo("Başarılı", "Test bildirimi gönderildi!")
        except Exception as e:
            messagebox.showerror("Hata", f"Bildirim gönderilemedi: {str(e)}")

    def add_process_to_monitor(self):
        selected = self.process_list.get()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen bir proses seçin")
            return
            
        try:
            process_name = selected.split(' (PID:')[0].strip()
            pid = int(selected.split('PID: ')[1].split(')')[0])
            
            if any(p['pid'] == pid for p in self.monitored_processes):
                messagebox.showinfo("Bilgi", "Bu proses zaten izleniyor")
                return
                
            self.monitored_processes.append({
                'name': process_name,
                'pid': pid,
                'added_time': datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            })
            
            messagebox.showinfo("Başarılı", f"{process_name} izlemeye alındı!")
        except Exception as e:
            messagebox.showerror("Hata", f"Proses seçilemedi: {str(e)}")

    def start_process_monitor(self):
        def monitor_loop():
            while self.ram_update_running:
                try:
                    self.check_monitored_processes()
                except Exception as e:
                    print(f"İzleme hatası: {str(e)}")
                time.sleep(10)
                
        threading.Thread(target=monitor_loop, daemon=True).start()

    def check_monitored_processes(self):
        for proc in list(self.monitored_processes):
            if not psutil.pid_exists(proc['pid']):
                self.send_process_notification(proc)
                self.monitored_processes.remove(proc)

    def send_process_notification(self, proc_info):
        if not self.discord_webhook:
            return
            
        message = (
            f"⚠️ **Uygulama Sonlandı!**\n"
            f"**İsim:** {proc_info['name']}\n"
            f"**PID:** {proc_info['pid']}\n"
            f"**Eklenme Zamanı:** {proc_info['added_time']}\n"
            f"**Kapanma Zamanı:** {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
        self.send_discord_message("Sistem Yöneticisi", message)

    def send_discord_message(self, username, message):
        payload = {
            "username": username,
            "content": message
        }
        
        try:
            response = requests.post(
                self.discord_webhook,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Discord bildirim hatası: {str(e)}")

    def create_bot_content(self, tab):
        frame = ctk.CTkFrame(master=tab)
        frame.pack(pady=20, padx=20, fill='both', expand=True)
        
        ctk.CTkLabel(frame, text="Discord Bot Token:").pack(pady=5)
        self.bot_token_entry = ctk.CTkEntry(frame, width=400)
        self.bot_token_entry.pack(pady=5)
        self.bot_token_entry.insert(0, self.bot_token)
        
        delete_frame = ctk.CTkFrame(frame)
        delete_frame.pack(pady=5)
        ctk.CTkLabel(delete_frame, text="Ekran Görüntüsü Silme Süresi (dakika):").pack(side='left', padx=5)
        self.delete_time_entry = ctk.CTkEntry(delete_frame, width=100)
        self.delete_time_entry.pack(side='left', padx=5)
        self.delete_time_entry.insert(0, self.screenshot_delete_time)
        
        self.bot_status = ctk.CTkLabel(frame, text="Bot Durumu: Kapalı")
        self.bot_status.pack(pady=5)
        
        self.bot_btn = ctk.CTkButton(
            frame, 
            text="Botu Başlat", 
            command=self.toggle_bot,
            fg_color="#5865F2"
        )
        self.bot_btn.pack(pady=10)
        
        ctk.CTkLabel(frame, text="Kullanılabilir Komutlar:").pack(pady=5)
        ctk.CTkLabel(frame, text="!screenshot - Ekran görüntüsü al ve belirtilen süre sonra sil").pack()

    def toggle_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            self.stop_bot()
        else:
            self.start_bot()
            
    def start_bot(self):
        self.bot_token = self.bot_token_entry.get().strip()
        if not self.bot_token:
            messagebox.showerror("Hata", "Lütfen bot token girin!")
            return
        try:
            intents = discord.Intents.default()
            intents.message_content = True
            self.bot = commands.Bot(
                command_prefix="!",
                intents=intents,
                help_command=None
            )
            self.bot.app = self
            
            @self.bot.event
            async def on_ready():
                self.bot_status.configure(
                    text=f"Bot Durumu: {self.bot.user.name} çevrimiçi",
                    text_color="#57F287"
                )
                self.bot_btn.configure(text="Botu Durdur", fg_color="#ed4245")
                self.save_config()
                
            @self.bot.command()
            async def screenshot(ctx):
                try:
                    try:
                        delete_time = int(ctx.bot.app.delete_time_entry.get().strip())
                        if delete_time <= 0:
                            delete_time = 60
                    except:
                        delete_time = 60

                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        ImageGrab.grab().save(tmp.name, "PNG")
                        message = await ctx.send(
                            content="📸 Ekran Görüntüsü:",
                            file=discord.File(tmp.name)
                        )
                    os.unlink(tmp.name)

                    await asyncio.sleep(delete_time * 60)
                    await message.delete()
                    
                except Exception as e:
                    await ctx.send(f"Hata: {str(e)}")

            self.bot_thread = threading.Thread(
                target=self.bot.run,
                args=(self.bot_token,),
                daemon=True
            )
            self.bot_thread.start()
            
        except Exception as e:
            messagebox.showerror("Hata", f"Bot başlatılamadı: {str(e)}")
            
    def stop_bot(self):
        if self.bot:
            self.bot_status.configure(text="Bot Durumu: Kapalı", text_color="white")
            self.bot_btn.configure(text="Botu Başlat", fg_color="#5865F2")
            self.bot.loop.create_task(self.bot.close())
            self.save_config()

    def save_config(self):
        config = {
            'discord_webhook': self.discord_webhook,
            'bot_token': self.bot_token,
            'screenshot_delete_time': self.delete_time_entry.get().strip()
        }
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            messagebox.showerror("Hata", f"Ayarlar kaydedilemedi: {str(e)}")

    def load_config(self):
        self.config = {}
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                    self.discord_webhook = self.config.get('discord_webhook', '')
                    self.bot_token = self.config.get('bot_token', '')
                    self.screenshot_delete_time = self.config.get('screenshot_delete_time', '60')
        except Exception as e:
            print(f"Ayarlar yüklenemedi: {str(e)}")

    def monitor_ram(self):
        def update_gui():
            if self.ram_update_running:
                ram_usage = psutil.virtual_memory().percent
                self.ram_progress.set(ram_usage / 100)
                self.ram_usage_label.configure(text=f"RAM Kullanımı: %{ram_usage:.1f}")
                if self.ram_clean_enabled and self.ram_threshold_entry.get().isdigit():
                    threshold = int(self.ram_threshold_entry.get())
                    if ram_usage >= threshold:
                        self.clean_ram()
                self.after(1000, update_gui)
        update_gui()

    def on_closing(self):
        self.ram_update_running = False
        self.destroy()

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = ShutdownApp()
    app.mainloop()