# -*- coding: utf-8 -*-
"""
scripts/create_desktop_shortcut.py
Creates a Desktop Shortcut for Asset Control Tower v4.8 using Win32 API.
"""

import os
import subprocess
import sys

# Windows CP949 콘솔 호환성
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    temp_lnk = os.path.join(desktop, "AssetControlTowerTemp.lnk")
    final_lnk = os.path.join(desktop, "🏛️ 자산관제탑.lnk")
    target = r"C:\cowork\myasset\run_control_tower.bat"
    working = r"C:\cowork\myasset"

    # 1. PowerShell WScript.Shell 로 임시 파일명 바로가기 생성
    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{temp_lnk}')
$s.TargetPath = '{target}'
$s.WorkingDirectory = '{working}'
$s.Description = '자산 관제탑 (Asset Control Tower v4.8) 원클릭 런처'
$s.IconLocation = 'shell32.dll, 44'
$s.Save()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)

    # 2. Python Win32 유니코드 API로 이모지 파일명으로 원자적 변경
    if os.path.exists(temp_lnk):
        if os.path.exists(final_lnk):
            os.remove(final_lnk)
        os.rename(temp_lnk, final_lnk)
        print(f"[성공] 바탕화면 바로가기 생성 완료: {final_lnk}")
    else:
        print("[오류] 임시 바로가기 파일 생성에 실패했습니다.")
        sys.exit(1)

if __name__ == "__main__":
    main()
