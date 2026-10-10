#Requires -Version 5.1
<#
.SYNOPSIS
  Pone la marca de CidIA en una copia de la app base (la carpeta app\ de la carga del instalador).

.DESCRIPTION
  La app base no pone icono a sus ventanas en Windows: Electron usa el del ejecutable, que es el de
  DeepSeek Harness, igual que la barra de tareas, Alt+Tab y el Administrador de tareas (que además
  muestra su descripción). La bandeja y los cuadros de diálogo usan resources\tray.ico y el panel
  «Acerca de», resources\icon.png. Este script, sobre la copia de CidIA y nunca sobre otra:

    1. cambia con rcedit (herramienta oficial de Electron), en una copia del ejecutable, su icono y
       sus datos de versión (FileDescription, ProductName, CompanyName, InternalName,
       OriginalFilename, LegalCopyright, FileVersion y ProductVersion);
    2. la deja con el nombre -Exe (CidIA.exe), el que se ve en el Administrador de tareas, y borra
       el original;
    3. sustituye resources\tray.ico y resources\icon.png por los de CidIA;
    4. corrige en resources\runtime\cli\bin\dsh.cmd la ruta al ejecutable renombrado;
    5. comprueba el resultado (icono incrustado = cidia.ico, datos de versión sin «DeepSeek»).

  No toca resources\app.asar. Cambiar los recursos del ejecutable invalida la firma Authenticode de
  DeepSeek (construir.ps1 la comprueba antes de llamar a este script). Electron no valida el
  ejecutable ni el asar al arrancar (fusible EnableEmbeddedAsarIntegrityValidation apagado, se
  comprueba aquí: si estuviera encendido, el script se para).

.PARAMETER App
  Carpeta de la app base, con el ejecutable original «DeepSeek Harness.exe».
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$App,
  [Parameter(Mandatory)] [string]$Rcedit,
  [Parameter(Mandatory)] [string]$Marca,
  [Parameter(Mandatory)] [string]$Version,
  [Parameter(Mandatory)] [string]$VersionWin,
  [Parameter(Mandatory)] [string]$Empresa,
  [Parameter(Mandatory)] [string]$Copyright,
  [string]$Exe = 'CidIA.exe',
  [string]$ExeOriginal = 'DeepSeek Harness.exe'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3
function Fallo([string]$texto) { throw "CidIA (marca de la app): $texto" }

$original = Join-Path $App $ExeOriginal
$destino = Join-Path $App $Exe
$recursos = Join-Path $App 'resources'
$ico = Join-Path $Marca 'cidia.ico'
$png = Join-Path $Marca 'png\cidia-512.png'
foreach ($f in $original, $Rcedit, $ico, $png, (Join-Path $recursos 'app.asar')) {
  if (-not (Test-Path $f)) { Fallo "no existe $f" }
}
if (Test-Path $destino) { Fallo "ya existe $destino" }

# Fusibles de Electron: con la validación de integridad del asar encendida, Electron comprobaría
# el app.asar contra un recurso del ejecutable. rcedit conserva los demás recursos, pero se exige
# que esté apagada para no depender de ello.
if (-not ('CidiaFusibles' -as [type])) {
  Add-Type -TypeDefinition @'
public static class CidiaFusibles {
  // Cadena de fusibles: centinela de 32 bytes, versión, número de fusibles y un byte por fusible.
  public static string Leer(byte[] b) {
    byte[] c = System.Text.Encoding.ASCII.GetBytes("dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX");
    for (int i = 0; i + c.Length + 2 < b.Length; i++) {
      int j = 0;
      while (j < c.Length && b[i + j] == c[j]) j++;
      if (j == c.Length) return System.Text.Encoding.ASCII.GetString(b, i + c.Length + 2, b[i + c.Length + 1]);
    }
    return null;
  }
}
'@
}
$fusibles = [CidiaFusibles]::Leer([IO.File]::ReadAllBytes($original))
if (-not $fusibles) { Fallo "no se encuentran los fusibles de Electron en $original" }
# Orden de la versión 1: RunAsNode, EnableCookieEncryption, EnableNodeOptionsEnvironmentVariable,
# EnableNodeCliInspectArguments, EnableEmbeddedAsarIntegrityValidation, ...
if ($fusibles.Length -lt 5 -or $fusibles[4] -eq [char]'1') {
  Fallo "el fusible EnableEmbeddedAsarIntegrityValidation está encendido ($fusibles): no se cambia el ejecutable"
}
[GC]::Collect()

# 1. icono y datos de versión
$cadenas = [ordered]@{
  FileDescription  = 'CidIA'
  ProductName      = 'CidIA'
  CompanyName      = $Empresa
  InternalName     = 'CidIA'
  OriginalFilename = $Exe
  LegalCopyright   = $Copyright
  FileVersion      = $Version
  ProductVersion   = $Version
}
# Sobre una copia: si algo falla, el original (firmado) queda intacto para volver a intentarlo.
$parcial = "$destino.parcial"
Copy-Item -Force $original $parcial
try {
  $argumentos = @($parcial, '--set-icon', $ico, '--set-file-version', $VersionWin, '--set-product-version', $VersionWin)
  foreach ($k in $cadenas.Keys) { $argumentos += @('--set-version-string', $k, $cadenas[$k]) }
  & $Rcedit @argumentos
  if ($LASTEXITCODE -ne 0) { Fallo "rcedit terminó con código $LASTEXITCODE" }
} catch {
  Remove-Item -Force $parcial -ErrorAction SilentlyContinue
  throw
}

# 2. nombre del ejecutable
Move-Item $parcial $destino
Remove-Item -Force $original

# 3. iconos de la bandeja (y de los cuadros de diálogo) y del panel «Acerca de»
Copy-Item -Force $ico (Join-Path $recursos 'tray.ico')
Copy-Item -Force $png (Join-Path $recursos 'icon.png')

# 4. orden «dsh» de la app (no la usa CidIA, pero no debe quedar rota)
$dshCmd = Join-Path $recursos 'runtime\cli\bin\dsh.cmd'
if (Test-Path $dshCmd) {
  $cmd = [IO.File]::ReadAllText($dshCmd)
  if ($cmd.Contains($ExeOriginal)) {
    [IO.File]::WriteAllText($dshCmd, $cmd.Replace($ExeOriginal, $Exe), (New-Object System.Text.UTF8Encoding($false)))
  }
}

# 5. comprobaciones
$info = (Get-Item $destino).VersionInfo
foreach ($k in 'FileDescription', 'ProductName', 'CompanyName', 'InternalName', 'OriginalFilename', 'LegalCopyright') {
  if ($info.$k -ne $cadenas[$k]) { Fallo "$k es «$($info.$k)», se esperaba «$($cadenas[$k])»" }
}
foreach ($k in 'FileDescription', 'ProductName', 'CompanyName', 'InternalName', 'OriginalFilename', 'LegalCopyright', 'FileVersion', 'ProductVersion', 'Comments') {
  if ([string]$info.$k -match 'DeepSeek') { Fallo "$k sigue diciendo «$($info.$k)»" }
}
& (Join-Path $PSScriptRoot 'icono-exe.ps1') -Exe $destino -Ico $ico
if ($LASTEXITCODE -ne 0) { Fallo "el icono incrustado en $destino no es cidia.ico" }
if (Test-Path $dshCmd) {
  if ([IO.File]::ReadAllText($dshCmd).Contains($ExeOriginal)) { Fallo "dsh.cmd sigue apuntando a $ExeOriginal" }
}
Write-Host "App con la marca de CidIA: $Exe · $($info.FileDescription) · $($info.CompanyName) · $($info.ProductVersion)"
