# Start an executable like Explorer would (optionally with a file, as in a drag and drop),
# capture only its Tk window to a PNG with PrintWindow, then close it.
# Usage: powershell -File tools/dev/capture_window.ps1 -Exe wa2html.exe [-Arg chat.zip] -Png window.png [-Wait 6]
param([Parameter(Mandatory = $true)][string]$Exe, [string]$Arg = "", [Parameter(Mandatory = $true)][string]$Png, [int]$Wait = 6)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinCapture {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public delegate bool EnumProc(IntPtr h, IntPtr p);
}
"@
[WinCapture]::SetProcessDPIAware() | Out-Null

if ($Arg) { $p = Start-Process -FilePath $Exe -ArgumentList "`"$Arg`"" -PassThru } else { $p = Start-Process -FilePath $Exe -PassThru }
Start-Sleep -Seconds $Wait

# The one-file program runs as two processes: the bootloader and its Python child.
$ids = @($p.Id) + @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($p.Id)" | ForEach-Object { $_.ProcessId })
$found = New-Object System.Collections.ArrayList
$callback = [WinCapture+EnumProc]{
  param($h, $x)
  $wpid = 0; [WinCapture]::GetWindowThreadProcessId($h, [ref]$wpid) | Out-Null
  if ($ids -contains $wpid -and [WinCapture]::IsWindowVisible($h)) {
    $t = New-Object System.Text.StringBuilder 256; [WinCapture]::GetWindowText($h, $t, 256) | Out-Null
    $c = New-Object System.Text.StringBuilder 256; [WinCapture]::GetClassName($h, $c, 256) | Out-Null
    [void]$found.Add([pscustomobject]@{ Handle = $h; Title = $t.ToString(); Class = $c.ToString() })
  }
  return $true
}
[WinCapture]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
"visible windows of the program:"
$found | ForEach-Object { "  [" + $_.Class + "] " + $_.Title }

$window = $found | Where-Object { $_.Class -eq "TkTopLevel" } | Select-Object -First 1
if ($window) {
  $r = New-Object WinCapture+RECT
  [WinCapture]::GetWindowRect($window.Handle, [ref]$r) | Out-Null
  $w = $r.R - $r.L; $h = $r.B - $r.T
  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  [WinCapture]::PrintWindow($window.Handle, $hdc, 2) | Out-Null
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
  "captured ${w}x${h} -> $Png"
} else {
  "no Tk window found"
}
foreach ($id in $ids) { & taskkill /F /T /PID $id 2>$null | Out-Null }
