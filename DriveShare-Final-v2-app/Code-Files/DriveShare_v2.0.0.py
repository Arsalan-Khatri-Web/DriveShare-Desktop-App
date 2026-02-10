import os, http.server, socket, qrcode, cgi, urllib.parse, re, json, subprocess, threading
from socketserver import ThreadingMixIn
import sys
from io import BytesIO
import base64

PORT = 8000

# Professional Path: PC aur Mobile dono ko handle karega
if os.name == 'nt': 
    ROOT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Drive_Share_Files")
else: 
    # Android ke liye specific path (Standard Shared Files)
    ROOT_DIR = "/sdcard/Drive_Share_Files" if os.path.exists("/sdcard") else "Shared_Files"

if not os.path.exists(ROOT_DIR):
    try: os.makedirs(ROOT_DIR)
    except: ROOT_DIR = "Shared_Files"; os.makedirs(ROOT_DIR, exist_ok=True)

def get_qr_base64(url):
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = socket.gethostbyname(socket.gethostname())
    finally:
        s.close()
    return ip

def get_resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

PUBLIC_URL = "Generating link..."

def start_cloudflare():
    global PUBLIC_URL
    cf_path = get_resource_path("cloudflared.exe")
    try:
        process = subprocess.Popen(
            [cf_path, 'tunnel', '--url', f'http://localhost:{PORT}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in process.stdout:
            if "trycloudflare.com" in line:
                public_url = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if public_url:
                    PUBLIC_URL = public_url.group(0)
                    print(f"="*100)
                    print(f"\n\tPUBLIC ACCESS : Share Your PC/Laptop Drive Globally Use Link OR Scan QRCode\n")
                    print(f"\tPublic URL : {PUBLIC_URL}\n")
                    print("="*100)
                    # Naya QR Code for Public Link
                    qr = qrcode.QRCode(box_size=2, border=10)
                    qr.add_data(PUBLIC_URL)
                    qr.print_ascii()
                    break
    except Exception as e:
        print(f"Cloudflare Error: {e}")
        
        
class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class DynamicSharedDriveHandler(http.server.SimpleHTTPRequestHandler):
    
    def get_size_format(self, b, factor=1024, suffix="B"):
        for unit in ["", "K", "M", "G", "T"]:
            if b < factor: return f"{b:.2f}{unit}{suffix}"
            b /= factor
        return f"{b:.2f}PB"

    def get_file_info(self, filename, full_path):
        ext = filename.split('.')[-1].lower()
        is_v = ext in ['mp4', 'mkv', 'mov', 'avi', 'webm']
        is_i = ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp']
        is_a = ext in ['mp3', 'wav', 'ogg', 'm4a', 'aac']
        icons = {'mp4': 'movie', 'jpg': 'image', 'pdf': 'picture_as_pdf', 'zip': 'inventory_2'}
        ic = icons.get(ext, 'insert_drive_file')
        col = '#5f6368'
        if is_i: ic = 'image'; col = '#ff9800'
        elif is_v: ic = 'movie'; col = '#e91e63'
        elif is_a: ic = 'music_note'; col = '#9c27b0'
        return ic, col, is_v, is_i, is_a, self.get_size_format(os.path.getsize(full_path)), ext.upper()

    def do_GET(self):
        try:
            if self.path.startswith('/download/'):
                f_rel = urllib.parse.unquote(self.path.replace('/download/', ''))
                f_full = os.path.join(ROOT_DIR, f_rel)
                if os.path.exists(f_full) and os.path.isfile(f_full):
                    size = os.path.getsize(f_full)
                    range_header = self.headers.get('Range')
                    start, end = 0, size - 1
                    if range_header:
                        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
                        if match:
                            start = int(match.group(1))
                            if match.group(2): end = int(match.group(2))
                    self.send_response(206 if range_header else 200)
                    self.send_header('Content-type', self.guess_type(f_full))
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                    self.send_header('Content-Length', str(end - start + 1))
                    self.end_headers()
                    with open(f_full, 'rb') as f:
                        f.seek(start)
                        self.wfile.write(f.read(end - start + 1))
                return
            
            query = urllib.parse.urlparse(self.path).query
            rel_path = urllib.parse.parse_qs(query).get('path', [''])[0]
            full_path = os.path.abspath(os.path.join(ROOT_DIR, rel_path))
            
            if os.path.isdir(full_path):
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(self.get_ui(rel_path, os.listdir(full_path)).encode('utf-8'))
        except Exception as e:
            print(f"GET Error: {e}")

    def do_POST(self):
        try:
            if self.path.startswith('/delete/'):
                f_rel = urllib.parse.unquote(self.path.replace('/delete/', ''))
                f_full = os.path.join(ROOT_DIR, f_rel)
                if os.path.exists(f_full) and os.path.isfile(f_full):
                    os.remove(f_full)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Deleted")
                return

            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST'})
            if 'file' in form:
                files = form['file']
                if not isinstance(files, list): files = [files]
                for item in files:
                    if item.filename:
                        target_path = os.path.join(ROOT_DIR, item.filename)
                        if os.path.exists(target_path):
                            dup_dir = os.path.join(ROOT_DIR, "Duplicates")
                            os.makedirs(dup_dir, exist_ok=True)
                            target_path = os.path.join(dup_dir, item.filename)
                        with open(target_path, 'wb') as f:
                            f.write(item.file.read())
                
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"Success")
        except Exception as e:
            print(f"❌ POST Error: {e}")

    def get_ui(self, current_rel_path, files):
        ip = get_ip()
        local_url = f"http://{ip}:{PORT}"
        local_qr = get_qr_base64(local_url)

        global PUBLIC_URL
        # Agar link ban gaya hai toh QR dikhayega warna loading text
        public_qr = get_qr_base64(PUBLIC_URL) if "http" in PUBLIC_URL else ""

        # Baki UI logic...
        ip = get_ip()
        local_url = f"http://{ip}:{PORT}"
        qr_img = get_qr_base64(local_url)
        
        is_root = current_rel_path == ""
        folder_display = "Home" if is_root else os.path.basename(current_rel_path)
        back_html = ""
        if not is_root:
            parent = os.path.dirname(current_rel_path)
            back_html = f'<div onclick="loadFolder(\'{parent}\')" style="display:flex; align-items:center; gap:8px; color:#1a73e8; cursor:pointer; margin-bottom:15px; font-weight:bold; font-size:14px;"><span class="material-icons">arrow_back</span> Back to Previous</div>'

        file_list_html = ""
        sorted_items = sorted(files, key=lambda x: os.path.isdir(os.path.join(ROOT_DIR, current_rel_path, x)), reverse=True)
        for f in sorted_items:
            full_path = os.path.join(ROOT_DIR, current_rel_path, f)
            rel_url = os.path.join(current_rel_path, f).replace("\\", "/")
            download_url = f"/download/{urllib.parse.quote(rel_url)}"
            safe_name = f.replace("'", "\\'")
            if os.path.isdir(full_path):
                file_list_html += f'''<li class="item" onclick="loadFolder('{rel_url}')"><span class="material-icons" style="color:#fcc934">folder</span><div class="file-details"><div class="name"><b>{f}</b></div><div class="meta">Folder</div></div></li>'''
            else:
                ic, col, is_v, is_i, is_a, f_size, f_fmt = self.get_file_info(f, full_path)
                file_list_html += f'''<li class="item">
                    <div style="display:flex; align-items:center; flex:1; min-width:0;" onclick="handleItemClick('{download_url}', '{is_v}', '{is_i}', '{is_a}', '{safe_name}')">
                        <span class="material-icons" style="color:{col}">{ic}</span>
                        <div class="file-details"><div class="name">{f}</div><div class="meta">{f_size} | {f_fmt}</div></div>
                    </div>
                    <a href="{download_url}" download="{f}" style="text-decoration:none; display:flex; align-items:center;"><span class="material-icons" style="color:#1a73e8; padding:5px;">file_download</span></a>
                    <span class="material-icons" style="color:#d93025; cursor:pointer; padding:5px;" onclick="showDeletePopup('{rel_url}', '{safe_name}')">delete_outline</span>
                </li>'''

        # Yahan return statement ko theek kiya gaya hai
        return f"""
        <html>
        <head>
            <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; background: #f8f9fa; margin: 0; }}
                .top-bar {{ background: white; padding: 12px 15px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 1px 3px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 100; }}
                .container {{ max-width: 1100px; margin: 15px auto; display: flex; flex-direction: column; gap: 15px; padding: 0 10px; }}
                @media (min-width: 850px) {{ .container {{ display: grid; grid-template-columns: 320px 1fr; align-items: start; }} .sidebar {{ position: sticky; top: 70px; }} }}
                .card {{ background: white; padding: 15px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e0e0e0; }}
                .item {{ background: white; margin-bottom: 10px; border-radius: 12px; border: 1px solid #e8eaed; display: flex; align-items: center; padding: 12px 10px; min-width: 0; transition: all 0.2s ease; }}
                .file-details {{ display: flex; flex-direction: column; overflow: hidden; flex: 1; margin-left: 10px; }}
                .name {{ font-size: 14px; color: #3c4043; word-wrap: break-word; word-break: break-all; }}
                .meta {{ font-size: 11px; color: #70757a; }}
                #progress-card {{ display: none; margin-top: 15px; }}
                .bar {{ background: #e8eaed; border-radius: 10px; height: 20px; overflow: hidden; margin: 10px 0; }}
                #fill {{ width: 0%; height: 100%; background: #1a73e8; transition: width 0.2s; display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: bold; }}
                #modal-overlay, #delete-overlay {{ display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.9); z-index:99999; justify-content:center; align-items:center; flex-direction: column; }}
                .media-obj {{ max-width: 98%; max-height: 85vh; border-radius: 5px; box-shadow: 0 0 50px rgba(0,0,0,0.8); display: none; }}
                ul {{padding: 0px; margin-top: -2px; list-style:none;}}
                .popup-card {{ background: white; padding: 25px; border-radius: 16px; margin:20px; max-width: 400px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }}
                .modal {{ display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:1000; justify-content:center; align-items:center; }}
                .modal-content {{ background:white; padding:20px; border-radius:15px; text-align:center; width:90%; max-width:400px; }}
                .qr-box {{ border:1px solid #ddd; padding:10px; border-radius:10px; margin-top:10px; }}
            </style>
        </head>
        <body>
            <div class="top-bar">
                <div style="display:flex; align-items:center; gap:5px; min-width:0; flex:1;"><span class="material-icons" style="color:#5f6368">folder</span><b>{folder_display}</b></div>
                <div style="font-size:11px; color:#70757a;">{len(files)} items</div>
            </div>
            <div class="container">

                <div id="qr-modal" class="modal" onclick="this.style.display='none'">
                    <div class="modal-content" onclick="event.stopPropagation()">
                        <h3 style="margin-top:0">Device Connections</h3>
                        <div class="qr-box">
                            <b>Local Link (Same Wi-Fi)</b>
                            <img src="data:image/png;base64,{local_qr}" style="width:150px; display:block; margin:10px auto;">
                            <a href="{local_url}" target="_blank" style="font-size:12px;">{local_url}</a>
                        </div>
                        <div class="qr-box">
                            <b>Global Link (Cloudflare)</b>
                            {f'<img src="data:image/png;base64,{public_qr}" style="width:150px; display:block; margin:10px auto;"><a href="{PUBLIC_URL}" target="_blank" style="font-size:12px;">{PUBLIC_URL}</a>' if public_qr else '<p>Generating tunnel...</p>'}
                        </div>
                        <button onclick="document.getElementById('qr-modal').style.display='none'" style="margin-top:15px; padding:8px 20px; border-radius:5px; border:none; background:#5f6368; color:white;">Close</button>
                    </div>
                    
                </div>
                
                <div class="sidebar"><div class="card">
                    <button onclick="document.getElementById('qr-modal').style.display='flex'" style="width:100%; padding:10px; background:#1a73e8; color:white; border:none; border-radius:8px; cursor:pointer; font-weight:bold; margin-bottom:10px;">📡 Connection Links</button>
                    <h3 style="margin:0 0 10px 0; font-size:15px; color:#1a73e8;">Storage Control</h3>
                    {back_html}
                    <input type="file" id="fInp" multiple style="font-size:12px; width:100%;">
                    <button style="background:#1a73e8;color:white;border:none;padding:10px;border-radius:6px;width:100%;cursor:pointer;font-weight:600;margin-top:10px;" onclick="upFiles()">Upload</button>
                    <div id="progress-card">
                        <div id="up-name" style="font-size:11px; font-weight:bold; overflow:hidden;">Uploading, Please wait...</div>
                        <div class="bar"><div id="fill">0%</div></div>
                        <div style="display:flex; justify-content:space-between; font-size:10px; color:#5f6368;"><span id="sp-lab">0 MB/s</span><span id="up-count">0/0</span></div>
                        <div style="text-align:center; margin-top:8px;"><small style="color:#d93025; cursor:pointer; font-weight:bold;" onclick="location.reload()">✕ CANCEL</small></div>
                    </div>
                </div></div>
                <div style="padding:0;"><ul>{file_list_html if file_list_html else "Empty"}</ul></div>
            </div>

            <div id="delete-overlay">
                <div class="popup-card">
                    <span class="material-icons" style="font-size:40px; color:#d93025;">report_problem</span>
                    <h3>Are you sure?</h3><p id="delete-text" style="font-size:14px; color:#5f6368;"></p>
                    <div style="display:flex; gap:10px; margin-top:20px; justify-content:center;">
                        <button onclick="closeDelete()" style="padding:10px 20px; border-radius:8px; border:none; cursor:pointer;">Cancel</button>
                        <button id="confirm-del" style="background:#d93025; color:white; padding:10px 20px; border-radius:8px; border:none; cursor:pointer; font-weight:bold;">Yes, Delete</button>
                    </div>
                </div>
            </div>

            <div id="modal-overlay" onclick="closeM()">
                <div style="position:fixed; top:15px; right:15px; color:white; font-size:40px; cursor:pointer; z-index:100000;">&times;</div>
                <video id="v-player" class="media-obj" controls onclick="event.stopPropagation()"></video>
                <img id="i-player" class="media-obj" onclick="event.stopPropagation()">
                <div id="a-container" style="display:none; color:white; text-align:center; width:90%;" onclick="event.stopPropagation()">
                    <h4 id="a-name"></h4><audio id="a-player" controls style="width:100%;"></audio>
                </div>
            </div>
        <footer style="margin-top: 50px; padding: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #777;">
            <p><b>Developer:</b> Arsalan Khatri</p>
            <p><b>Powered by:</b> AK Deep Knowledge</p>
            <p>© 2024 AK Deep Knowledge. All Rights Reserved.</p>
        </footer>
            <script>
                let st_time;
                function handleItemClick(url, isV, isI, isA, name) {{
                    const v = document.getElementById('v-player'), i = document.getElementById('i-player'), a = document.getElementById('a-container'), ap = document.getElementById('a-player');
                    v.style.display = i.style.display = a.style.display = 'none'; v.src = i.src = ap.src = "";
                    if (isV === 'True') {{ v.src = url; v.style.display = 'block'; v.play(); }}
                    else if (isI === 'True') {{ i.src = url; i.style.display = 'block'; }}
                    else if (isA === 'True') {{ ap.src = url; a.style.display = 'block'; document.getElementById('a-name').innerText = name; ap.play(); }}
                    document.getElementById('modal-overlay').style.display = 'flex';
                }}
                function closeM() {{ document.getElementById('modal-overlay').style.display = 'none'; document.getElementById('v-player').pause(); document.getElementById('a-player').pause(); }}
                function closeDelete() {{ document.getElementById('delete-overlay').style.display = 'none'; }}
                function showDeletePopup(path, name) {{
                    document.getElementById('delete-text').innerText = "Delete '" + name + "' permanently?";
                    document.getElementById('delete-overlay').style.display = 'flex';
                    document.getElementById('confirm-del').onclick = async () => {{
                        await fetch('/delete/' + encodeURIComponent(path), {{method: 'POST'}});
                        location.reload();
                    }};
                }}
                async function upFiles() {{
                    const f = document.getElementById('fInp').files; if (!f.length) return;
                    document.getElementById('progress-card').style.display = 'block';
                    for (let j = 0; j < f.length; j++) {{
                        const fd = new FormData(); fd.append('file', f[j]); const xhr = new XMLHttpRequest(); st_time = Date.now();
                        document.getElementById('up-count').innerText = (j+1) + "/" + f.length;
                        await new Promise(r => {{
                            xhr.upload.onprogress = e => {{
                                if (e.lengthComputable) {{
                                    const p = Math.round((e.loaded/e.total)*100); const sec = (Date.now()-st_time)/1000;
                                    const sp = (e.loaded/(1024*1024*(sec||0.1))).toFixed(1);
                                    document.getElementById('fill').style.width = p+'%'; document.getElementById('fill').innerText = p+'%';
                                    document.getElementById('sp-lab').innerText = sp + " MB/s";
                                }}
                            }};
                            xhr.onreadystatechange = () => {{ if(xhr.readyState==4) r(); }};
                            xhr.open('POST', '/', true); xhr.send(fd);
                        }});
                    }}
                    location.reload();
                }}
                function loadFolder(p) {{ window.location.href = "/?path=" + encodeURIComponent(p); }}
            </script>
        </body>
        </html>
        """


# def run():
#     ip = get_ip()
#     threading.Thread(target=start_cloudflare, daemon=True).start()
#     print(f"\n🚀 DRIVE SHARE PRO v2.0 READY\n📍 Local: http://{ip}:{PORT}")
#     qr = qrcode.QRCode(box_size=2, border=4)
#     qr.add_data(f"http://{ip}:{PORT}")
#     qr.print_ascii()
    
    
#     ThreadedHTTPServer(('', PORT), DynamicSharedDriveHandler).serve_forever()

def run():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]
    except: ip = '127.0.0.1'
    finally: s.close()
    
    # Start Cloudflare
    threading.Thread(target=start_cloudflare, daemon=True).start()
    print("\n" + "="*100)
    print("\n\t\tWELCOME TO: DRIVE SHARE")
    print("\t\tApp Developed by: Arsalan Khatri")
    print("\t\tCompany: AK Deep Knowledge")
    print("\t\t© 2025 AK Deep Knowledge. All Rights Reserved.")
    print("\n" + "="*100+"\n")
    print(f"\tDRIVE READY TO SHARE USE LINK OR SCAN QRCode")
    print(f"\tConnectivity: Same Wi-Fi Required Offline Mode Supported (No Internet Needed)\n") 
    print(f"\tLocal URL : http://{ip}:{PORT}")
    print("\n"+"="*100)
    
    # Local QR Code
    qr = qrcode.QRCode(box_size=2, border=10)
    qr.add_data(f"http://{ip}:{PORT}")
    qr.print_ascii()
    
    ThreadedHTTPServer(('', PORT), DynamicSharedDriveHandler).serve_forever()

if __name__ == "__main__":
    run()