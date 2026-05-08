import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from processor import ProcessSettings, ProcessingCancelled, process_batch

APP_TITLE = 'White BG Remover Pro'
SETTINGS_FILE = str(Path.home() / 'white_bg_remover_pro_settings.json')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry('980x760')
        self.minsize(860, 640)
        self.configure(bg='#16181d')

        self.style = ttk.Style(self)
        try:
            self.style.theme_use('clam')
        except Exception:
            pass
        self._configure_style()

        self.queue = queue.Queue()
        self.worker = None
        self.cancel_flag = False
        self.last_result = None

        self.vars = {
            'input_dir': tk.StringVar(),
            'workspace_dir': tk.StringVar(),
            'threshold': tk.IntVar(value=36),
            'choke_px': tk.IntVar(value=1),
            'feather_px': tk.DoubleVar(value=1.25),
            'canvas_size': tk.IntVar(value=1024),
            'trim': tk.BooleanVar(value=True),
            'copy_review': tk.BooleanVar(value=True),
            'overwrite': tk.BooleanVar(value=True),
        }

        self._build_ui()
        self._load_settings()
        self.after(120, self._poll_queue)

    def _configure_style(self):
        self.style.configure('.', background='#16181d', foreground='#e7e7e7', fieldbackground='#1f2430')
        self.style.configure('TFrame', background='#16181d')
        self.style.configure('TLabelframe', background='#16181d', foreground='#f5f5f5')
        self.style.configure('TLabelframe.Label', background='#16181d', foreground='#f5f5f5', font=('Segoe UI', 11, 'bold'))
        self.style.configure('TLabel', background='#16181d', foreground='#e7e7e7', font=('Segoe UI', 10))
        self.style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'), foreground='#ffffff')
        self.style.configure('SubHeader.TLabel', font=('Segoe UI', 10), foreground='#bcc2d0')
        self.style.configure('TButton', font=('Segoe UI', 10, 'bold'), padding=8, background='#3d5af1')
        self.style.map('TButton', background=[('active', '#5572ff')])
        self.style.configure('Accent.TButton', font=('Segoe UI', 10, 'bold'), padding=10, background='#5b8cff', foreground='#ffffff')
        self.style.map('Accent.TButton', background=[('active', '#6d99ff')])
        self.style.configure('Danger.TButton', background='#8f3f3f', foreground='#ffffff')
        self.style.map('Danger.TButton', background=[('active', '#a64c4c')])
        self.style.configure('TEntry', fieldbackground='#1f2430', foreground='#ffffff', insertcolor='#ffffff')
        self.style.configure('TCheckbutton', background='#16181d', foreground='#e7e7e7')
        self.style.configure('Horizontal.TProgressbar', troughcolor='#1f2430', background='#5b8cff', bordercolor='#1f2430', lightcolor='#5b8cff', darkcolor='#5b8cff')

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill='both', expand=True)

        ttk.Label(root, text=APP_TITLE, style='Header.TLabel').pack(anchor='w')
        ttk.Label(
            root,
            text='Production-ready batch workflow: transparent PNG output, QA previews, review-needed sorting, failed-file sorting, and CSV logging.',
            style='SubHeader.TLabel'
        ).pack(anchor='w', pady=(2, 14))

        paths = ttk.LabelFrame(root, text='1) Folders', padding=12)
        paths.pack(fill='x', pady=(0, 10))
        self._folder_row(paths, 0, 'Input folder', self.vars['input_dir'], self.browse_input)
        self._folder_row(paths, 1, 'Workspace folder', self.vars['workspace_dir'], self.browse_workspace)
        ttk.Label(paths, text='Workspace subfolders created automatically: output_png, qa_previews, review_needed, failed, logs').grid(row=2, column=0, columnspan=3, sticky='w', pady=(10, 0))
        paths.columnconfigure(1, weight=1)

        settings = ttk.LabelFrame(root, text='2) Processing settings', padding=12)
        settings.pack(fill='x', pady=(0, 10))
        self._spin_row(settings, 0, 'Background threshold', self.vars['threshold'], 1, 120)
        self._spin_row(settings, 1, 'Edge choke (px)', self.vars['choke_px'], 0, 5)
        self._spin_row(settings, 2, 'Feather (px)', self.vars['feather_px'], 0.0, 5.0, increment=0.25)
        self._spin_row(settings, 3, 'Canvas size', self.vars['canvas_size'], 256, 4096, increment=64)
        ttk.Checkbutton(settings, text='Trim and center asset on square canvas', variable=self.vars['trim']).grid(row=4, column=0, columnspan=2, sticky='w', pady=(8, 4))
        ttk.Checkbutton(settings, text='Copy originals of flagged files into review_needed', variable=self.vars['copy_review']).grid(row=5, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Checkbutton(settings, text='Overwrite existing output files', variable=self.vars['overwrite']).grid(row=6, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Label(settings, text='Suggested starting values for white/gray backgrounds: threshold 36, choke 1, feather 1.25, canvas 1024').grid(row=7, column=0, columnspan=3, sticky='w', pady=(8, 0))
        settings.columnconfigure(1, weight=1)

        actions = ttk.Frame(root)
        actions.pack(fill='x', pady=(0, 10))
        self.start_btn = ttk.Button(actions, text='Start Batch', style='Accent.TButton', command=self.start_batch)
        self.start_btn.pack(side='left')
        self.cancel_btn = ttk.Button(actions, text='Cancel', style='Danger.TButton', command=self.cancel_batch, state='disabled')
        self.cancel_btn.pack(side='left', padx=(8, 0))
        ttk.Button(actions, text='Save Settings', command=self._save_settings).pack(side='left', padx=(8, 0))
        ttk.Button(actions, text='Open Workspace', command=self.open_workspace).pack(side='left', padx=(8, 0))

        self.progress_var = tk.StringVar(value='Ready.')
        ttk.Label(root, textvariable=self.progress_var).pack(anchor='w')
        self.progress = ttk.Progressbar(root, orient='horizontal', mode='determinate', maximum=100)
        self.progress.pack(fill='x', pady=(6, 10))

        summary = ttk.Frame(root)
        summary.pack(fill='x', pady=(0, 8))
        self.processed_var = tk.StringVar(value='Processed: 0')
        self.review_var = tk.StringVar(value='Review needed: 0')
        self.failed_var = tk.StringVar(value='Failed: 0')
        ttk.Label(summary, textvariable=self.processed_var).pack(side='left', padx=(0, 16))
        ttk.Label(summary, textvariable=self.review_var).pack(side='left', padx=(0, 16))
        ttk.Label(summary, textvariable=self.failed_var).pack(side='left')

        log_frame = ttk.LabelFrame(root, text='3) Live log', padding=10)
        log_frame.pack(fill='both', expand=True)
        self.log_text = tk.Text(log_frame, wrap='word', bg='#101319', fg='#f0f0f0', insertbackground='#ffffff', relief='flat', font=('Consolas', 10))
        self.log_text.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        scrollbar.pack(side='right', fill='y')
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _folder_row(self, parent, row, label, var, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=5)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky='ew', pady=5)
        ttk.Button(parent, text='Browse', command=command).grid(row=row, column=2, sticky='ew', padx=(8, 0), pady=5)

    def _spin_row(self, parent, row, label, var, frm, to, increment=1):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=4)
        spin = ttk.Spinbox(parent, from_=frm, to=to, textvariable=var, increment=increment, width=12)
        spin.grid(row=row, column=1, sticky='w', pady=4)

    def browse_input(self):
        path = filedialog.askdirectory(title='Choose input folder')
        if path:
            self.vars['input_dir'].set(path)

    def browse_workspace(self):
        path = filedialog.askdirectory(title='Choose workspace folder')
        if path:
            self.vars['workspace_dir'].set(path)

    def open_workspace(self):
        path = self.vars['workspace_dir'].get().strip()
        if not path:
            messagebox.showinfo(APP_TITLE, 'Choose a workspace folder first.')
            return
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        os.startfile(path)

    def get_settings(self):
        return ProcessSettings(
            input_dir=self.vars['input_dir'].get().strip(),
            workspace_dir=self.vars['workspace_dir'].get().strip(),
            threshold=int(self.vars['threshold'].get()),
            choke_px=int(self.vars['choke_px'].get()),
            feather_px=float(self.vars['feather_px'].get()),
            canvas_size=int(self.vars['canvas_size'].get()),
            trim=bool(self.vars['trim'].get()),
            copy_originals_to_review=bool(self.vars['copy_review'].get()),
            overwrite=bool(self.vars['overwrite'].get()),
        )

    def validate_inputs(self, settings):
        if not settings.input_dir or not os.path.isdir(settings.input_dir):
            raise ValueError('Pick a valid input folder.')
        if not settings.workspace_dir:
            raise ValueError('Pick a valid workspace folder.')
        os.makedirs(settings.workspace_dir, exist_ok=True)

    def start_batch(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            settings = self.get_settings()
            self.validate_inputs(settings)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return

        self._save_settings()
        self.cancel_flag = False
        self.last_result = None
        self.log_text.delete('1.0', 'end')
        self.progress['value'] = 0
        self.processed_var.set('Processed: 0')
        self.review_var.set('Review needed: 0')
        self.failed_var.set('Failed: 0')
        self.progress_var.set('Starting batch...')
        self.start_btn.configure(state='disabled')
        self.cancel_btn.configure(state='normal')

        def worker_fn():
            try:
                result = process_batch(
                    settings,
                    progress_callback=lambda i, total, msg: self.queue.put(('progress', i, total, msg)),
                    log_callback=lambda msg: self.queue.put(('log', msg)),
                    cancel_check=lambda: self.cancel_flag,
                )
                self.queue.put(('done', result))
            except ProcessingCancelled as e:
                self.queue.put(('cancelled', str(e)))
            except Exception as e:
                self.queue.put(('error', str(e)))

        self.worker = threading.Thread(target=worker_fn, daemon=True)
        self.worker.start()

    def cancel_batch(self):
        self.cancel_flag = True
        self.progress_var.set('Cancelling after current file...')
        self.cancel_btn.configure(state='disabled')

    def _poll_queue(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                kind = msg[0]
                if kind == 'log':
                    self.append_log(msg[1])
                elif kind == 'progress':
                    _, i, total, text = msg
                    pct = 0 if total == 0 else (i / total) * 100.0
                    self.progress['value'] = pct
                    self.progress_var.set(text)
                elif kind == 'done':
                    self.last_result = msg[1]
                    counts = self.last_result['counts']
                    self.processed_var.set(f"Processed: {counts.get('processed', 0)}")
                    self.review_var.set(f"Review needed: {counts.get('review_needed', 0)}")
                    self.failed_var.set(f"Failed: {counts.get('failed', 0)}")
                    self.progress['value'] = 100
                    self.progress_var.set('Batch complete.')
                    self.append_log('')
                    self.append_log('Open the workspace to review your output folders and CSV log.')
                    self._unlock_ui()
                    messagebox.showinfo(APP_TITLE, 'Batch complete.')
                elif kind == 'cancelled':
                    self.append_log(msg[1])
                    self.progress_var.set('Batch cancelled.')
                    self._unlock_ui()
                    messagebox.showinfo(APP_TITLE, 'Batch cancelled.')
                elif kind == 'error':
                    self.append_log(f'ERROR: {msg[1]}')
                    self.progress_var.set('Error.')
                    self._unlock_ui()
                    messagebox.showerror(APP_TITLE, msg[1])
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _unlock_ui(self):
        self.start_btn.configure(state='normal')
        self.cancel_btn.configure(state='disabled')

    def append_log(self, text):
        self.log_text.insert('end', text + '\n')
        self.log_text.see('end')

    def _save_settings(self):
        data = {k: v.get() for k, v in self.vars.items()}
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        if not os.path.isfile(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, v in data.items():
                if k in self.vars:
                    self.vars[k].set(v)
        except Exception:
            pass


if __name__ == '__main__':
    app = App()
    app.mainloop()
