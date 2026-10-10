# Síntesis con las voces de Windows (solo para comparar; ver README, apartado de licencias).
#   powershell -NoProfile -ExecutionPolicy Bypass -File voz_windows.ps1 -Motor onecore -Voz "Microsoft Laura" -Texto texto.txt -Salida salida.wav [-Velocidad 1.0]
#   -Motor onecore: Windows.Media.SpeechSynthesis (Helena, Laura, Pablo)
#   -Motor sapi:    System.Speech (Microsoft Helena Desktop)
param(
  [ValidateSet('onecore', 'sapi')][string]$Motor = 'onecore',
  [string]$Voz = 'Microsoft Laura',
  [Parameter(Mandatory = $true)][string]$Texto,
  [Parameter(Mandatory = $true)][string]$Salida,
  [double]$Velocidad = 1.0
)
$ErrorActionPreference = 'Stop'
$contenido = [IO.File]::ReadAllText($Texto, [Text.Encoding]::UTF8)

if ($Motor -eq 'sapi') {
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($Voz)
  $s.Rate = [int][Math]::Round(($Velocidad - 1.0) * 10)
  $s.SetOutputToWaveFile($Salida)
  $s.Speak($contenido)
  $s.Dispose()
  exit 0
}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Esperar($operacion, [Type]$tipo) {
  $t = $asTask.MakeGenericMethod($tipo).Invoke($null, @($operacion))
  $null = $t.Wait(-1)
  return $t.Result
}
$s = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.DisplayName -eq $Voz } | Select-Object -First 1
if (-not $v) { throw "No está la voz $Voz" }
$s.Voice = $v
$s.Options.SpeakingRate = $Velocidad
$flujo = Esperar ($s.SynthesizeTextToStreamAsync($contenido)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$lector = New-Object Windows.Storage.Streams.DataReader($flujo.GetInputStreamAt(0))
$n = [uint32]$flujo.Size
$null = Esperar ($lector.LoadAsync($n)) ([uint32])
$bytes = New-Object byte[] $n
$lector.ReadBytes($bytes)
[IO.File]::WriteAllBytes($Salida, $bytes)
