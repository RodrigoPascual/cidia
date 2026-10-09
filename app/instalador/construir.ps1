#Requires -Version 5.1
<#
.SYNOPSIS
  Construye el instalador de CidIA: app\instalador\salida\CidIA-Setup.exe.

.DESCRIPTION
  1. Descarga (o reutiliza de la caché) el instalador OFICIAL fijado de DeepSeek Harness
     0.2.0-rc.2 y comprueba su tamaño, su sha512 (fijado aquí y contra el feed oficial) y su
     firma Authenticode.
  2. Extrae su carga útil (app-64.7z) con 7-Zip SIN ejecutar el instalador oficial y quita
     resources\app-update.yml, para que la app no se actualice sola.
  3. Prepara la carpeta de carga: plugin CidIA, plantillas del perfil, marca y textos.
  4. Genera plantillas.nsh: el instalador y el lanzador escriben la configuración en UTF-8 a
     partir de las plantillas de app\perfil (NSIS no escribe UTF-8 por sí mismo).
  5. Descarga NSIS 3.11 portable (zip oficial de SourceForge, sha256 fijado) en la carpeta de
     herramientas, sin instalarlo en el sistema, y compila el lanzador (CidIA.exe) y el
     instalador.

  Todo lo descargado y generado queda fuera de git, en -Trabajo (por defecto
  %LOCALAPPDATA%\CidIA-construccion). El resultado va a app\instalador\salida (ignorada).

.PARAMETER Perfil
  Perfil de construcción (perfiles\<nombre>.json): dirección del servidor por defecto y
  modelo por defecto. «pruebas» apunta al servidor de pruebas por el túnel SSH.

.PARAMETER Trabajo
  Carpeta de trabajo fuera del repositorio (caché de descargas, herramientas y carga).

.PARAMETER SieteZip
  Ruta de 7z.exe. Por defecto, la de 7-Zip instalado o la del PATH.

.PARAMETER Rapido
  Compresión zlib en lugar de LZMA: compila mucho antes, el instalador ocupa más. Para pruebas.

.PARAMETER SinPruebas
  No ejecuta las pruebas del plugin (node --test) antes de construir.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File app\instalador\construir.ps1
  powershell -ExecutionPolicy Bypass -File app\instalador\construir.ps1 -Perfil empresa
#>
[CmdletBinding()]
param(
  [string]$Perfil = 'pruebas',
  [string]$Trabajo = (Join-Path $env:LOCALAPPDATA 'CidIA-construccion'),
  [string]$SieteZip = '',
  [switch]$Rapido,
  [switch]$SinPruebas
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version 3
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ------------------------------------------------------------------ versiones fijadas
$DshVersion = '0.2.0-rc.2'
$DshUrl = "https://download.deepseek.com/dsh-desk/bin/win-x64/deepseek-harness-$DshVersion-win-x64.exe"
$DshFeed = 'https://download.deepseek.com/dsh-desk/feeds/win-x64/nightly.yml'
$DshTamano = 289313640
$DshSha512 = 'raIlxMQd9ESXgktmViW7QwVLcjBR5JIsrNOu+SpelY8kskdSr2H51/f+ey1EqFI/eIIrKQCuRANMeb5SptRZcg=='
$DshFirmante = 'Hangzhou DeepSeek Artificial Intelligence Co., Ltd.'
$NsisVersion = '3.11'
$NsisUrl = 'https://sourceforge.net/projects/nsis/files/NSIS%203/3.11/nsis-3.11.zip/download'
$NsisSha256 = 'c7d27f780ddb6cffb4730138cd1591e841f4b7edb155856901cdf5f214394fa1'

# ------------------------------------------------------------------ rutas
$Instalador = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$AppRepo = Join-Path $Repo 'app'
$Cache = Join-Path $Trabajo 'cache'
$Herramientas = Join-Path $Trabajo 'herramientas'
$Extraccion = Join-Path $Trabajo 'extraccion'
$Carga = Join-Path $Trabajo 'carga'
$Salida = Join-Path $Instalador 'salida'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)

function Paso([string]$texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Fallo([string]$texto) { throw "CidIA: $texto" }

function Descargar([string]$url, [string]$destino) {
  $parcial = "$destino.parcial"
  if (Test-Path $parcial) { Remove-Item $parcial -Force }
  $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
  if ($curl) {
    & $curl.Source -L --fail --silent --show-error --retry 3 -o $parcial $url
    if ($LASTEXITCODE -ne 0) { Fallo "no se pudo descargar $url (curl $LASTEXITCODE)" }
  } else {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $parcial
  }
  Move-Item $parcial $destino -Force
}

function Sha512Base64([string]$fichero) {
  $hex = (Get-FileHash -Algorithm SHA512 -Path $fichero).Hash
  $bytes = New-Object byte[] ($hex.Length / 2)
  for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [Convert]::ToByte($hex.Substring($i * 2, 2), 16) }
  return [Convert]::ToBase64String($bytes)
}

function ComprobarFirma([string]$fichero) {
  $firma = Get-AuthenticodeSignature -FilePath $fichero
  if ($firma.Status -ne 'Valid') { Fallo "la firma de $fichero no es válida ($($firma.Status))" }
  if ($firma.SignerCertificate.Subject -notlike "*$DshFirmante*") {
    Fallo "$fichero no está firmado por $DshFirmante ($($firma.SignerCertificate.Subject))"
  }
}

# ------------------------------------------------------------------ 0. perfil y comprobaciones
Paso "Perfil de construcción: $Perfil"
$rutaPerfil = Join-Path $Instalador "perfiles\$Perfil.json"
if (-not (Test-Path $rutaPerfil)) { Fallo "no existe el perfil $rutaPerfil" }
$conf = Get-Content -Raw -Encoding UTF8 $rutaPerfil | ConvertFrom-Json
foreach ($campo in 'servidor', 'modelo', 'modelo_nombre', 'contexto') {
  if (-not $conf.$campo) { Fallo "al perfil $Perfil le falta '$campo'" }
}
$paquete = Get-Content -Raw -Encoding UTF8 (Join-Path $AppRepo 'plugins\cidia\package.json') | ConvertFrom-Json
$Version = $paquete.version
$VersionWin = (($Version -split '[-+]')[0] + '.0')
Write-Host "CidIA $Version · servidor por defecto $($conf.servidor) · modelo $($conf.modelo)"

if (-not $SieteZip) {
  $candidatos = @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe")
  $SieteZip = ($candidatos | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1)
  if (-not $SieteZip) { $SieteZip = (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source }
}
if (-not $SieteZip -or -not (Test-Path $SieteZip)) { Fallo 'no se encuentra 7-Zip (7z.exe). Instálalo o pasa -SieteZip.' }

foreach ($d in $Cache, $Herramientas, $Extraccion, $Salida) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

if (-not $SinPruebas) {
  Paso 'Pruebas del plugin (node --test)'
  $node = Get-Command node.exe -ErrorAction SilentlyContinue
  if ($node) {
    Push-Location (Join-Path $AppRepo 'plugins\cidia')
    try {
      & $node.Source --test 'pruebas/*.test.*' | Select-Object -Last 9
      if ($LASTEXITCODE -ne 0) { Fallo 'las pruebas del plugin han fallado' }
    } finally { Pop-Location }
  } else {
    Write-Warning 'Node no está en el PATH: se omiten las pruebas del plugin.'
  }
}

# ------------------------------------------------------------------ 1. instalador oficial
Paso "DeepSeek Harness $DshVersion (instalador oficial)"
$oficial = Join-Path $Cache "deepseek-harness-$DshVersion-win-x64.exe"
if ((Test-Path $oficial) -and ((Get-Item $oficial).Length -ne $DshTamano)) { Remove-Item $oficial -Force }
if (-not (Test-Path $oficial)) {
  Write-Host "Descargando $DshUrl"
  Descargar $DshUrl $oficial
}
if ((Get-Item $oficial).Length -ne $DshTamano) { Fallo "tamaño inesperado de $oficial" }
$sha = Sha512Base64 $oficial
if ($sha -ne $DshSha512) { Fallo "el sha512 de $oficial no coincide con el fijado" }
try {
  $feed = (Invoke-WebRequest -UseBasicParsing -Uri $DshFeed -TimeoutSec 20).Content
  if ($feed -is [byte[]]) { $feed = [Text.Encoding]::UTF8.GetString($feed) }
  $versionFeed = [regex]::Match($feed, '(?m)^version:\s*(\S+)').Groups[1].Value
  $shaFeed = [regex]::Match($feed, '(?ms)^sha512:\s*(?:>-\s*)?(\S+)').Groups[1].Value
  if ($versionFeed -eq $DshVersion) {
    if ($shaFeed -ne $sha) { Fallo 'el sha512 no coincide con el del feed oficial' }
    Write-Host "sha512 comprobado contra el feed oficial ($versionFeed)"
  } else {
    Write-Warning "El feed oficial ya anuncia $versionFeed; se usa el sha512 fijado de $DshVersion."
  }
} catch [System.Net.WebException] {
  Write-Warning "No se pudo leer el feed oficial ($($_.Exception.Message)); se usa el sha512 fijado."
}
ComprobarFirma $oficial
Write-Host "Firma válida: $DshFirmante"

# ------------------------------------------------------------------ 2. carga útil de la app
Paso 'App base (app-64.7z)'
$marca = Join-Path $Carga 'app\.cidia-origen'
$origen = "$DshVersion $DshSha512"
$appCarga = Join-Path $Carga 'app'
if ((Test-Path $marca) -and ((Get-Content -Raw $marca).Trim() -eq $origen)) {
  Write-Host 'Carga útil ya extraída (caché).'
} else {
  $paquete7z = Join-Path $Extraccion 'app-64.7z'
  if (Test-Path $paquete7z) { Remove-Item $paquete7z -Force }
  & $SieteZip e -y "-o$Extraccion" $oficial '$PLUGINSDIR\app-64.7z' | Out-Null
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $paquete7z)) { Fallo 'no se pudo extraer app-64.7z del instalador oficial' }
  if (Test-Path $appCarga) { Remove-Item $appCarga -Recurse -Force }
  Write-Host 'Extrayendo la app (1,1 GB)…'
  & $SieteZip x -y "-o$appCarga" $paquete7z | Out-Null
  if ($LASTEXITCODE -ne 0) { Fallo 'no se pudo extraer app-64.7z' }
  Remove-Item $paquete7z -Force
  Set-Content -Path $marca -Value $origen -Encoding ASCII
}
$actualizador = Join-Path $appCarga 'resources\app-update.yml'
if (Test-Path $actualizador) { Remove-Item $actualizador -Force }
ComprobarFirma (Join-Path $appCarga 'DeepSeek Harness.exe')
if (Test-Path $actualizador) { Fallo 'app-update.yml sigue en la carga' }
Write-Host 'Sin app-update.yml: la app no buscará actualizaciones.'

# ------------------------------------------------------------------ 3. plugin, perfil, marca y textos
Paso 'Carga de CidIA'
foreach ($d in 'plugin', 'perfil', 'marca', 'textos') {
  $ruta = Join-Path $Carga $d
  if (Test-Path $ruta) { Remove-Item $ruta -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $ruta | Out-Null
}
$pluginOrigen = Join-Path $AppRepo 'plugins\cidia'
$pluginCarga = Join-Path $Carga 'plugin\cidia'
New-Item -ItemType Directory -Force -Path $pluginCarga | Out-Null
foreach ($f in 'package.json', 'index.js', 'client.js', 'cordis.patch.yml', 'locale', 'idioma') {
  Copy-Item -Recurse -Path (Join-Path $pluginOrigen $f) -Destination $pluginCarga
}
Copy-Item -Recurse -Path (Join-Path $AppRepo 'perfil\*') -Destination (Join-Path $Carga 'perfil')
# Los .env.plantilla empiezan por punto: Copy-Item con * no siempre los incluye.
Copy-Item -Force (Join-Path $AppRepo 'perfil\home\.env.plantilla') (Join-Path $Carga 'perfil\home\.env.plantilla')
foreach ($f in 'cidia.ico', 'instalador-bienvenida.bmp', 'instalador-cabecera.bmp', 'cidia.svg') {
  Copy-Item (Join-Path $AppRepo "marca\$f") (Join-Path $Carga 'marca')
}
# La página de licencia de NSIS (Unicode) lee UTF-16LE con BOM.
$licencia = [IO.File]::ReadAllText((Join-Path $Instalador 'textos\licencia.txt'), $Utf8)
[IO.File]::WriteAllText((Join-Path $Carga 'textos\licencia.txt'), $licencia.Replace("`r`n", "`n").Replace("`n", "`r`n"), (New-Object System.Text.UnicodeEncoding($false, $true)))

# ------------------------------------------------------------------ 4. plantillas.nsh
Paso 'Plantillas de configuración (plantillas.nsh)'
function NsisCadena([string]$texto) {
  return $texto.Replace('$', '$$').Replace('"', '$\"').Replace("`t", '$\t')
}
$fijos = @{
  '{{MODELO}}'        = (NsisCadena ([string]$conf.modelo))
  '{{MODELO_NOMBRE}}' = (NsisCadena ([string]$conf.modelo_nombre))
  '{{CONTEXTO}}'      = (NsisCadena ([string][int]$conf.contexto))
}
$variables = @{ '{{GATEWAY_URL}}' = '$Servidor'; '{{RUTA_PLUGIN}}' = '$RutaPlugin' }
$plantillas = @(
  @{ Macro = 'CIDIA_ESCRIBIR_ENV'; Origen = 'home\.env.plantilla' },
  @{ Macro = 'CIDIA_ESCRIBIR_PATCH_HOME'; Origen = 'home\cordis.patch.yml' },
  @{ Macro = 'CIDIA_ESCRIBIR_PAQUETE_PERFIL'; Origen = 'profiles\desktop\package.json' },
  @{ Macro = 'CIDIA_ESCRIBIR_PNPM'; Origen = 'profiles\desktop\pnpm-workspace.yaml' },
  @{ Macro = 'CIDIA_ESCRIBIR_PATCH_USUARIO'; Origen = 'profiles\desktop\cordis.patch.yml' }
)
$nsh = New-Object System.Text.StringBuilder
[void]$nsh.AppendLine('; Generado por construir.ps1 a partir de app\perfil. No editar a mano.')
[void]$nsh.AppendLine("; Perfil de construcción: $Perfil")
foreach ($p in $plantillas) {
  $lineas = [IO.File]::ReadAllLines((Join-Path $AppRepo "perfil\$($p.Origen)"), $Utf8)
  [void]$nsh.AppendLine("!macro $($p.Macro) DESTINO")
  [void]$nsh.AppendLine('  Push $R8')
  [void]$nsh.AppendLine('  Push $R9')
  [void]$nsh.AppendLine('  ClearErrors')
  [void]$nsh.AppendLine('  FileOpen $R8 "${DESTINO}" w')
  [void]$nsh.AppendLine('  ${IfNot} ${Errors}')
  foreach ($linea in $lineas) {
    $l = NsisCadena $linea
    foreach ($k in $fijos.Keys) { $l = $l.Replace($k, $fijos[$k]) }
    foreach ($k in $variables.Keys) { $l = $l.Replace($k, $variables[$k]) }
    if ($l -match '\{\{[A-Z_]+\}\}') { Fallo "marcador sin valor en $($p.Origen): $($Matches[0])" }
    if ($l.Length -gt 900) { Fallo "línea demasiado larga para NSIS en $($p.Origen)" }
    [void]$nsh.AppendLine("    StrCpy `$R9 `"$l`$\n`"")
    [void]$nsh.AppendLine('    Call EscribirUTF8')
  }
  [void]$nsh.AppendLine('    FileClose $R8')
  [void]$nsh.AppendLine('  ${EndIf}')
  [void]$nsh.AppendLine('  Pop $R9')
  [void]$nsh.AppendLine('  Pop $R8')
  [void]$nsh.AppendLine('!macroend')
}
$rutaNsh = Join-Path $Carga 'plantillas.nsh'
[IO.File]::WriteAllText($rutaNsh, $nsh.ToString(), $Utf8Bom)

# ------------------------------------------------------------------ 5. NSIS y compilación
Paso "NSIS $NsisVersion (portable)"
$nsisDir = Join-Path $Herramientas "nsis-$NsisVersion"
$makensis = Join-Path $nsisDir 'makensis.exe'
if (-not (Test-Path $makensis)) {
  $descarga = Join-Path $Herramientas 'descarga-nsis'
  New-Item -ItemType Directory -Force -Path $descarga | Out-Null
  $zip = Join-Path $descarga "nsis-$NsisVersion.zip"
  if (-not (Test-Path $zip)) { Descargar $NsisUrl $zip }
  if ((Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower() -ne $NsisSha256) {
    Remove-Item $zip -Force
    Fallo 'el sha256 del zip de NSIS no coincide con el publicado'
  }
  Expand-Archive -Path $zip -DestinationPath $Herramientas -Force
}
if (-not (Test-Path $makensis)) { Fallo "no se encuentra $makensis" }

$comunes = @('/V2', '/INPUTCHARSET', 'UTF8', "/DVERSION=$Version", "/DVERSION_WIN=$VersionWin",
  "/DSERVIDOR=$($conf.servidor)", "/DPLANTILLAS=$rutaNsh")
Push-Location $Instalador
try {
  Paso 'Lanzador (CidIA.exe)'
  & $makensis @comunes "/DSALIDA=$(Join-Path $Carga 'CidIA.exe')" "/DICONO=$(Join-Path $Carga 'marca\cidia.ico')" 'lanzador.nsi'
  if ($LASTEXITCODE -ne 0) { Fallo 'no se pudo compilar el lanzador' }

  Paso 'Instalador (CidIA-Setup.exe)'
  $setup = Join-Path $Salida 'CidIA-Setup.exe'
  $extra = @()
  if ($Rapido) { $extra += '/XSetCompressor /FINAL zlib' }
  $inicio = Get-Date
  & $makensis @extra @comunes "/DCARGA=$Carga" "/DSALIDA=$setup" 'CidIA.nsi'
  if ($LASTEXITCODE -ne 0) { Fallo 'no se pudo compilar el instalador' }
} finally { Pop-Location }

$info = Get-Item $setup
$hash = (Get-FileHash -Algorithm SHA256 $setup).Hash.ToLower()
Paso 'Listo'
Write-Host ("{0} · {1:N1} MB · {2:N0} s" -f $info.FullName, ($info.Length / 1MB), ((Get-Date) - $inicio).TotalSeconds)
Write-Host "SHA-256: $hash"
Set-Content -Path (Join-Path $Salida 'CidIA-Setup.exe.sha256') -Value "$hash  CidIA-Setup.exe" -Encoding ASCII
