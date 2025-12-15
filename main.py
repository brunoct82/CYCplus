import asyncio
import struct
import time
import datetime
import os
import flet as ft
from bleak import BleakClient

# --- CONFIGURAÇÕES ---
DEVICE_ADDRESS = "FA:CF:AF:49:95:5B"  # Seu Cycplus
WHEEL_CIRCUMFERENCE = 2.096           # Roda 700c

# --- ESTADO GLOBAL ---
current_speed = 0.0
average_speed = 0.0
total_distance = 0.0

# Cronometragem
elapsed_seconds = 0
last_tick_time = None
is_running = False     
is_paused = False      
auto_pause_active = False 
auto_pause_enabled = False 

# Memória do Sensor e Watchdog
prev_wheel_revs = None
prev_wheel_time = None
last_packet_time = 0.0 

# Dados para o Arquivo (Time, Speed(km/h), Dist(km))
track_points = []
start_datetime = None 

async def main(page: ft.Page):
    global current_speed, average_speed, total_distance, elapsed_seconds
    global is_running, is_paused, auto_pause_enabled, track_points
    global prev_wheel_revs, prev_wheel_time, start_datetime, last_packet_time

    # --- TELA ---
    page.title = "Cycplus Indoor TCX"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window_width = 400
    page.window_height = 850
    page.scroll = ft.ScrollMode.HIDDEN

    # --- WIDGETS ---
    icon_status = ft.Icon(name=ft.Icons.BLUETOOTH_DISABLED, color=ft.Colors.RED_400)
    txt_status = ft.Text("Desconectado", color=ft.Colors.RED_400, size=12)
    
    def on_autopause_change(e):
        global auto_pause_enabled
        auto_pause_enabled = chk_autopause.value
        page.update()

    chk_autopause = ft.Checkbox(label="Auto-Pause (2.5s)", value=True, on_change=on_autopause_change)

    txt_speed = ft.Text("0.0", size=90, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_400)
    lbl_kmh = ft.Text("km/h", size=20, color=ft.Colors.GREY_500)

    txt_avg = ft.Text("0.0", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_300)
    lbl_avg = ft.Text("Média", size=12, color=ft.Colors.GREY_500)

    txt_dist = ft.Text("0.00", size=30, weight=ft.FontWeight.BOLD)
    lbl_dist = ft.Text("Distância (km)", size=12, color=ft.Colors.GREY_500)
    
    txt_time = ft.Text("00:00", size=30, weight=ft.FontWeight.BOLD)
    lbl_time = ft.Text("Tempo", size=12, color=ft.Colors.GREY_500)

    # --- FUNÇÕES ---
    def toggle_pause(e):
        global is_paused, is_running
        if not is_running and total_distance == 0: return
        is_paused = not is_paused
        if is_paused:
            btn_pause.text = "Retomar"
            btn_pause.icon = ft.Icons.PLAY_ARROW
            btn_pause.bgcolor = ft.Colors.GREEN_900
            page.snack_bar = ft.SnackBar(ft.Text("⏸️ Pausado"))
        else:
            btn_pause.text = "Pausar"
            btn_pause.icon = ft.Icons.PAUSE
            btn_pause.bgcolor = ft.Colors.ORANGE_900
            page.snack_bar = ft.SnackBar(ft.Text("▶️ Retomado"))
        page.snack_bar.open = True
        page.update()

    def stop_ride(e):
        global is_running, is_paused
        if not is_running and total_distance == 0: return
        is_running = False
        is_paused = True 
        btn_pause.disabled = True
        btn_stop.disabled = True
        btn_save.disabled = False
        btn_reset.disabled = False
        page.snack_bar = ft.SnackBar(ft.Text("⏹️ Finalizado! Salve o arquivo."), bgcolor=ft.Colors.BLUE_900)
        page.snack_bar.open = True
        page.update()

    def reset_ride(e):
        global total_distance, elapsed_seconds, track_points, current_speed, average_speed
        global prev_wheel_revs, prev_wheel_time, is_running, is_paused, start_datetime
        total_distance = 0.0
        elapsed_seconds = 0
        current_speed = 0.0
        average_speed = 0.0
        track_points = []
        prev_wheel_revs = None
        prev_wheel_time = None
        start_datetime = None
        is_running = False
        is_paused = False
        txt_dist.value = "0.00"
        txt_time.value = "00:00"
        txt_speed.value = "0.0"
        txt_avg.value = "0.0"
        btn_pause.disabled = False
        btn_pause.text = "Pausar"
        btn_pause.icon = ft.Icons.PAUSE
        btn_pause.bgcolor = ft.Colors.ORANGE_800
        btn_stop.disabled = False
        btn_save.disabled = True 
        page.update()

    def export_tcx(e):
        # MUDANÇA PRINCIPAL: EXPORTAR PARA TCX EM VEZ DE GPX
        if not track_points:
            page.snack_bar = ft.SnackBar(ft.Text("⚠️ Sem dados!"), open=True)
            page.update()
            return

        try:
            base_path = os.getcwd()
            now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"Indoor_Cycplus_{now_str}.tcx"
            full_path = os.path.join(base_path, filename)
            
            # Formatação do Tempo Total
            total_seconds = elapsed_seconds
            
            # Início do XML TCX
            # Strava adora esse formato para Indoor
            tcx_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Biking">
      <Id>{start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")}</Id>
      <Lap StartTime="{start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")}">
        <TotalTimeSeconds>{total_seconds:.1f}</TotalTimeSeconds>
        <DistanceMeters>{total_distance * 1000:.1f}</DistanceMeters>
        <Calories>0</Calories>
        <Intensity>Active</Intensity>
        <TriggerMethod>Manual</TriggerMethod>
        <Track>
"""
            tcx_footer = """        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""
            track_str = []
            
            for pt in track_points:
                t_iso = pt['time'].strftime("%Y-%m-%dT%H:%M:%SZ")
                dist_meters = pt['dist'] * 1000
                speed_mps = pt['speed'] / 3.6
                
                # A mágica acontece aqui: DistanceMeters diz ao Strava quanto você andou
                # mesmo sem GPS.
                point_xml = f"""          <Trackpoint>
            <Time>{t_iso}</Time>
            <DistanceMeters>{dist_meters:.2f}</DistanceMeters>
            <Extensions>
               <TPX xmlns="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
                 <Speed>{speed_mps:.2f}</Speed>
               </TPX>
            </Extensions>
          </Trackpoint>"""
                track_str.append(point_xml)

            # Grava o arquivo
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(tcx_header + "\n".join(track_str) + tcx_footer)
            
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"✅ TCX SALVO!\n{full_path}", size=12, weight=ft.FontWeight.BOLD), 
                bgcolor=ft.Colors.GREEN_700, 
                open=True,
                duration=5000
            )
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"❌ Erro: {ex}"), bgcolor=ft.Colors.RED_700, open=True)
        
        page.update()

    # --- BOTÕES ---
    btn_pause = ft.ElevatedButton("Pausar", icon=ft.Icons.PAUSE, bgcolor=ft.Colors.ORANGE_800, color=ft.Colors.WHITE, on_click=toggle_pause, width=130)
    btn_stop = ft.ElevatedButton("Parar", icon=ft.Icons.STOP, bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, on_click=stop_ride, width=130)
    btn_save = ft.ElevatedButton("Salvar TCX", icon=ft.Icons.SAVE, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, on_click=export_tcx, disabled=True, width=130)
    btn_reset = ft.ElevatedButton("Resetar", icon=ft.Icons.RESTART_ALT, bgcolor=ft.Colors.GREY_800, color=ft.Colors.WHITE, on_click=reset_ride, width=130)

    # --- LAYOUT ---
    layout = ft.Column(
        controls=[
            ft.Row([icon_status, txt_status, ft.Container(width=20), chk_autopause], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=10),
            ft.Column([txt_speed, lbl_kmh], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(height=10),
            ft.Column([txt_avg, lbl_avg], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(height=30),
            ft.Row([
                    ft.Column([txt_dist, lbl_dist], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(width=50),
                    ft.Column([txt_time, lbl_time], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=40),
            ft.Row([btn_pause, btn_stop], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=10),
            ft.Row([btn_save, btn_reset], alignment=ft.MainAxisAlignment.CENTER),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    page.add(layout)

    # --- DADOS ---
    def process_data(sender, data):
        global current_speed, total_distance, elapsed_seconds, average_speed
        global prev_wheel_revs, prev_wheel_time, start_datetime
        global is_running, auto_pause_active, last_packet_time

        if is_paused or (not is_running and total_distance > 0): return 

        flags = data[0]
        if flags & 0x01: # Speed
            last_packet_time = time.time()
            w_revs, w_time = struct.unpack('<IH', data[1:7])

            if prev_wheel_revs is None:
                prev_wheel_revs = w_revs
                prev_wheel_time = w_time
                return

            rev_diff = w_revs - prev_wheel_revs
            if rev_diff < 0: rev_diff += 4294967296
            time_diff = w_time - prev_wheel_time
            if time_diff < 0: time_diff += 65536

            if time_diff > 3072: 
                prev_wheel_revs = w_revs
                prev_wheel_time = w_time
                return
            
            auto_pause_active = False
            
            if start_datetime is None:
                start_datetime = datetime.datetime.utcnow()
            
            time_sec = time_diff / 1024.0
            if time_sec > 0:
                speed_mps = (rev_diff * WHEEL_CIRCUMFERENCE) / time_sec
                kmh = speed_mps * 3.6
                
                if kmh < 120: 
                    current_speed = kmh
                    dist_add = (rev_diff * WHEEL_CIRCUMFERENCE) / 1000.0
                    total_distance += dist_add
                    # Agora salvamos pontos mais detalhados para o TCX
                    track_points.append({'time': datetime.datetime.utcnow(), 'speed': kmh, 'dist': total_distance})

            prev_wheel_revs = w_revs
            prev_wheel_time = w_time

    async def bluetooth_loop():
        global is_running
        while True:
            try:
                txt_status.value = "Buscando..."
                txt_status.color = ft.Colors.ORANGE_400
                page.update()
                async with BleakClient(DEVICE_ADDRESS) as client:
                    is_running = True 
                    icon_status.name = ft.Icons.BLUETOOTH_CONNECTED
                    icon_status.color = ft.Colors.GREEN_400
                    txt_status.value = "Conectado"
                    txt_status.color = ft.Colors.GREEN_400
                    page.update()
                    await client.start_notify("00002a5b-0000-1000-8000-00805f9b34fb", process_data)
                    while client.is_connected:
                        await asyncio.sleep(1)
            except Exception as e:
                is_running = False
                icon_status.name = ft.Icons.BLUETOOTH_DISABLED
                icon_status.color = ft.Colors.RED_400
                txt_status.value = "Reconectando..."
                page.update()
                await asyncio.sleep(3)

    async def ui_loop():
        global elapsed_seconds, last_tick_time, current_speed, auto_pause_active
        last_tick_time = time.time()
        while True:
            now = time.time()
            dt = now - last_tick_time
            last_tick_time = now

            if is_running and (now - last_packet_time) > 2.5:
                current_speed = 0.0
                if auto_pause_enabled: auto_pause_active = True
            
            if is_running and not is_paused:
                if not (auto_pause_enabled and auto_pause_active):
                    elapsed_seconds += dt

            mins, secs = divmod(int(elapsed_seconds), 60)
            hours, mins = divmod(mins, 60)
            txt_time.value = f"{hours:02}:{mins:02}:{secs:02}" if hours > 0 else f"{mins:02}:{secs:02}"

            if auto_pause_active or is_paused:
                txt_speed.value = "0.0"
                txt_speed.color = ft.Colors.GREY_700
            else:
                txt_speed.value = f"{current_speed:.1f}"
                txt_speed.color = ft.Colors.CYAN_400

            txt_dist.value = f"{total_distance:.2f}"
            if elapsed_seconds > 0:
                avg = total_distance / (elapsed_seconds / 3600.0)
                average_speed = avg
                txt_avg.value = f"{avg:.1f}"
            
            page.update()
            await asyncio.sleep(0.2)

    await asyncio.gather(bluetooth_loop(), ui_loop())

ft.app(target=main, view=ft.WEB_BROWSER, port=8080, host="127.0.0.1")
