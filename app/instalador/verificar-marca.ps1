#Requires -Version 5.1
<#
.SYNOPSIS
  Comprueba que una instalación de CidIA no se presenta en Windows como DeepSeek Harness: nombre,
  icono y datos de versión del ejecutable de la app, iconos de la bandeja, accesos directos con el
  AppUserModelID de CidIA y, si la app está abierta, el AppUserModelID con el que la agrupa la
  barra de tareas. Lo llama verificar.mjs; también se puede ejecutar solo.
  Escribe una línea «OK  …» o «FALLO …» por comprobación; código de salida = número de fallos.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File app\instalador\verificar-marca.ps1
#>
[CmdletBinding()]
param([string]$Instalacion = (Join-Path $env:LOCALAPPDATA 'Programs\CidIA'))
$ErrorActionPreference = 'Stop'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
# Salida en UTF-8 también cuando la lee otro programa (verificar.mjs).
try { [Console]::OutputEncoding = $Utf8 } catch { }
$script:fallos = 0
function Comprobar([bool]$ok, [string]$texto, [string]$detalle = '') {
  $linea = $(if ($ok) { 'OK   ' } else { 'FALLO' }) + " $texto" + $(if ($detalle) { " · $detalle" } else { '' })
  Write-Output $linea
  if (-not $ok) { $script:fallos++ }
}
function Definicion([string]$nombre) {
  $t = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'comun.nsh'), $Utf8)
  return [regex]::Match($t, '(?m)^!define\s+' + [regex]::Escape($nombre) + '\s+"([^"]*)"').Groups[1].Value
}
$exeNombre = Definicion 'CIDIA_EXE_APP'
$exeAnterior = Definicion 'CIDIA_EXE_APP_ANTERIOR'
$aumid = Definicion 'CIDIA_AUMID'
$exe = Join-Path $Instalacion "app\$exeNombre"
$ico = Join-Path $Instalacion 'cidia.ico'

# Ejecutable de la app: nombre, datos de versión e icono incrustado.
Comprobar ((Test-Path $exe) -and -not (Test-Path (Join-Path $Instalacion "app\$exeAnterior"))) "ejecutable de la app app\$exeNombre (sin $exeAnterior)"
if (Test-Path $exe) {
  $v = (Get-Item $exe).VersionInfo
  $cadenas = @($v.CompanyName, $v.FileDescription, $v.ProductName, $v.InternalName, $v.OriginalFilename, $v.LegalCopyright, $v.FileVersion, $v.ProductVersion, $v.Comments)
  Comprobar ($v.FileDescription -eq 'CidIA' -and $v.ProductName -eq 'CidIA' -and -not (($cadenas -join ' ') -match 'DeepSeek')) 'datos de versión del ejecutable' "$($v.FileDescription) · $($v.ProductName) · $($v.CompanyName) · $($v.ProductVersion)"
  $null = & (Join-Path $PSScriptRoot 'icono-exe.ps1') -Exe $exe -Ico $ico 6>$null
  Comprobar ($LASTEXITCODE -eq 0) 'icono del ejecutable (ventana, Alt+Tab, Administrador de tareas) = cidia.ico'
}
$tray = Join-Path $Instalacion 'app\resources\tray.ico'
Comprobar ((Test-Path $tray) -and (Get-FileHash $tray).Hash -eq (Get-FileHash $ico).Hash) 'icono de la bandeja y de los diálogos (resources\tray.ico) = cidia.ico'

# Accesos directos: al lanzador, con el icono y el AppUserModelID de CidIA.
$shell = New-Object -ComObject Shell.Application
$wsh = New-Object -ComObject WScript.Shell
foreach ($lnk in (Join-Path ([Environment]::GetFolderPath('Programs')) 'CidIA.lnk'), (Join-Path ([Environment]::GetFolderPath('Desktop')) 'CidIA.lnk')) {
  if (-not (Test-Path $lnk)) { Comprobar $false "acceso directo $lnk" 'no existe'; continue }
  $a = $wsh.CreateShortcut($lnk)
  $id = $shell.Namespace((Split-Path $lnk)).ParseName((Split-Path $lnk -Leaf)).ExtendedProperty('System.AppUserModel.ID')
  Comprobar ($a.TargetPath -eq (Join-Path $Instalacion 'CidIA.exe') -and $a.IconLocation -like "$ico,*" -and $id -eq $aumid) "acceso directo $(Split-Path (Split-Path $lnk) -Leaf)\CidIA.lnk" "AppUserModelID $id"
}

# App abierta: AppUserModelID que le asigna la barra de tareas (IApplicationResolver, la interfaz
# del shell que usa la barra de tareas; no documentada, por eso solo avisa si no está).
$raiz = (Join-Path $Instalacion 'app\').ToLowerInvariant()
$principal = @(Get-CimInstance Win32_Process | Where-Object {
  $_.ExecutablePath -and $_.ExecutablePath.ToLowerInvariant().StartsWith($raiz) -and $_.CommandLine -notmatch '--type=' -and $_.CommandLine -match '--user-data-dir' })
if ($principal.Count -eq 0) {
  Write-Output 'AVISO CidIA no está abierta: no se comprueba la barra de tareas'
} else {
  $p = Get-Process -Id $principal[0].ProcessId
  Comprobar ($p.Description -eq 'CidIA' -and $p.ProcessName -eq [IO.Path]::GetFileNameWithoutExtension($exeNombre)) 'proceso en el Administrador de tareas' "$($p.ProcessName).exe · $($p.Description)"
  try {
    if (-not ('CidiaResolver' -as [type])) {
      Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("DE25675A-72DE-44b4-9373-05170450C140"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ICidiaApplicationResolver8 {
  [PreserveSig] int GetAppIDForShortcut(IntPtr psi, out IntPtr id);
  [PreserveSig] int GetAppIDForShortcutObject(IntPtr psl, IntPtr psi, out IntPtr id);
  [PreserveSig] int GetAppIDForWindow(IntPtr hwnd, out IntPtr id, out int noPin, out int explicitId, out int embedded);
  [PreserveSig] int GetAppIDForProcess(uint pid, out IntPtr id, out int noPin, out int explicitId, out int embedded);
}
public static class CidiaResolver {
  public static string Proceso(uint pid) {
    var r = (ICidiaApplicationResolver8)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("660b90c8-73a9-4b58-8cae-355b7f55341b")));
    IntPtr id; int noPin, ex, emb;
    if (r.GetAppIDForProcess(pid, out id, out noPin, out ex, out emb) != 0) return null;
    string s = Marshal.PtrToStringUni(id); Marshal.FreeCoTaskMem(id);
    return (ex != 0 ? "explícito " : "implícito ") + s;
  }
}
'@
    }
    $id = [CidiaResolver]::Proceso([uint32]$principal[0].ProcessId)
    Comprobar ($id -eq "explícito $aumid") 'AppUserModelID de la ventana en la barra de tareas' $id
    $dsh = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like '*\Programs\DeepSeek Harness\*' -and $_.CommandLine -notmatch '--type=' })
    if ($dsh.Count) {
      $idDsh = [CidiaResolver]::Proceso([uint32]$dsh[0].ProcessId)
      Comprobar ($idDsh -ne $id) 'no se agrupa con DeepSeek Harness en la barra de tareas' "DeepSeek Harness: $idDsh"
    }
  } catch {
    Write-Output "AVISO no se pudo consultar el AppUserModelID de la barra de tareas ($($_.Exception.Message))"
  }
}
exit $script:fallos
