; lanzador.nsi: CidIA.exe, el lanzador de la app (sin ventana).
;
; Un acceso directo de Windows no puede fijar variables de entorno y la app base solo lee su
; carpeta de datos de DSH_HOME, así que los accesos directos abren este lanzador, que:
;   1. comprueba y repara el perfil: que package.json siga incluyendo el bundle cidia (la
;      recuperación tras un fallo de la app lo quita), que exista el enlace al plugin y que
;      estén el .env y la capa home;
;   2. fija DSH_HOME, DSH_TELEMETRY_DISABLED=1 y la red (el servidor CidIA va sin proxy y lo
;      demás que salga por Node, como la política de actualización, va a un sumidero local);
;   3. abre la app con --user-data-dir propio: la instancia única de Electron va por esa
;      carpeta, así CidIA no choca con una DeepSeek Harness instalada en el mismo usuario;
;   4. si en el equipo hay otra app que usa el protocolo dsh://, se lo devuelve (la app base
;      lo registra a su nombre al arrancar).
; Los argumentos que reciba se pasan a la app (p. ej. --remote-debugging-port=9333).
;
; Lo compila construir.ps1 con /D: SALIDA, ICONO, SERVIDOR, VERSION y PLANTILLAS.

Unicode true
ManifestDPIAware true
RequestExecutionLevel user
SilentInstall silent
SetCompressor /SOLID lzma

!ifndef VERSION
  !define VERSION "0.1.0"
!endif
!ifndef VERSION_WIN
  !define VERSION_WIN "0.1.0.0"
!endif
!ifndef SERVIDOR
  !define SERVIDOR "http://127.0.0.1:18700"
!endif
!ifndef SALIDA
  !define SALIDA "CidIA.exe"
!endif
!ifndef ICONO
  !define ICONO "..\marca\cidia.ico"
!endif
!ifndef PLANTILLAS
  !error "Falta /DPLANTILLAS=<plantillas.nsh> (lo genera construir.ps1)"
!endif

Name "CidIA"
Caption "CidIA"
OutFile "${SALIDA}"
Icon "${ICONO}"

VIProductVersion "${VERSION_WIN}"
VIAddVersionKey /LANG=0 "ProductName" "CidIA"
VIAddVersionKey /LANG=0 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=0 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=0 "FileDescription" "CidIA, copiloto de conocimiento industrial"
VIAddVersionKey /LANG=0 "LegalCopyright" "CidIA. Incluye DeepSeek Harness (licencia MIT)."

!include comun.nsh

Var Servidor
Var RutaPlugin
Var App
Var Anterior

!insertmacro CIDIA_DEFINIR_UTF8 ""
!insertmacro CIDIA_DEFINIR_ENLACES ""
!insertmacro CIDIA_DEFINIR_PROTOCOLO ""
!include "${PLANTILLAS}"

; ¿Incluye package.json del perfil el bundle cidia? Busca una línea que sea solo "cidia" (un
; elemento de dsh.profile.bundles; la dependencia es "cidia": "link:...").   ->  $R3 = 1 / 0
Function PerfilTieneCidia
  Push $0
  Push $1
  StrCpy $R3 "0"
  ClearErrors
  FileOpen $0 "${CIDIA_DATOS}\profiles\desktop\package.json" r
  ${IfNot} ${Errors}
    ${Do}
      ClearErrors
      FileRead $0 $1
      ${If} ${Errors}
        ${ExitDo}
      ${EndIf}
      ${TrimNewLines} "$1" $1
      ${WordReplace} "$1" " " "" "+" $1
      ${WordReplace} "$1" "$\t" "" "+" $1
      ${If} $1 == '"cidia"'
      ${OrIf} $1 == '"cidia",'
        StrCpy $R3 "1"
        ${ExitDo}
      ${EndIf}
    ${Loop}
    FileClose $0
  ${EndIf}
  ClearErrors
  Pop $1
  Pop $0
FunctionEnd

Function Reparar
  CreateDirectory "${CIDIA_DATOS}\profiles\desktop\node_modules"
  Call PerfilTieneCidia
  ${If} $R3 != "1"
    !insertmacro CIDIA_ESCRIBIR_PAQUETE_PERFIL "${CIDIA_DATOS}\profiles\desktop\package.json"
  ${EndIf}
  ${IfNot} ${FileExists} "${CIDIA_DATOS}\profiles\desktop\pnpm-workspace.yaml"
    !insertmacro CIDIA_ESCRIBIR_PNPM "${CIDIA_DATOS}\profiles\desktop\pnpm-workspace.yaml"
  ${EndIf}
  ${IfNot} ${FileExists} "${CIDIA_DATOS}\.env"
    !insertmacro CIDIA_ESCRIBIR_ENV "${CIDIA_DATOS}\.env"
  ${EndIf}
  ${IfNot} ${FileExists} "${CIDIA_DATOS}\cordis.patch.yml"
    !insertmacro CIDIA_ESCRIBIR_PATCH_HOME "${CIDIA_DATOS}\cordis.patch.yml"
  ${EndIf}
  ${IfNot} ${FileExists} "${CIDIA_ENLACE_PLUGIN}\package.json"
    StrCpy $R0 "${CIDIA_ENLACE_PLUGIN}"
    StrCpy $R1 "$EXEDIR\plugins\cidia"
    Call CrearEnlace
  ${EndIf}
FunctionEnd

; Red de la app: solo el servidor CidIA y el propio equipo.
;  · NO_PROXY con el servidor CidIA y el bucle local: el modelo, las herramientas MCP y las
;    llamadas internas de la app van directas.
;  · Todo lo demás que salga por fetch de Node (proceso principal y Host) va a un «proxy
;    sumidero» en 127.0.0.1:9, donde no escucha nadie: la conexión se rechaza al momento. Así
;    se corta la consulta de la política de actualización obligatoria de la app base
;    (harness.deepseek.com/api/v0/check_client_update, desde el proceso principal), que va
;    dentro del app.asar y no se puede apagar por configuración. Sin respuesta, la app no se
;    bloquea. Node 24 (Electron 44) solo aplica HTTP(S)_PROXY con NODE_USE_ENV_PROXY=1. El
;    navegador de la app (Chromium) no lee estas variables en Windows: no le afecta.
Function PrepararRed
  Push $0
  Push $1
  StrCpy $0 "$Servidor"
  ${WordReplace} "$0" "https://" "" "+" $0
  ${WordReplace} "$0" "http://" "" "+" $0
  ${WordFind} "$0" "/" "+1{" $0
  ${WordFind} "$0" ":" "+1{" $0
  ReadEnvStr $1 "NO_PROXY"
  ${If} $1 == ""
    StrCpy $1 "$0,127.0.0.1,localhost,::1"
  ${Else}
    StrCpy $1 "$1,$0,127.0.0.1,localhost,::1"
  ${EndIf}
  System::Call 'kernel32::SetEnvironmentVariable(t "NO_PROXY", t r1) i'
  System::Call 'kernel32::SetEnvironmentVariable(t "NODE_USE_ENV_PROXY", t "1") i'
  System::Call 'kernel32::SetEnvironmentVariable(t "HTTP_PROXY", t "http://127.0.0.1:9") i'
  System::Call 'kernel32::SetEnvironmentVariable(t "HTTPS_PROXY", t "http://127.0.0.1:9") i'
  System::Call 'kernel32::SetEnvironmentVariable(t "ALL_PROXY", p 0) i'
  ClearErrors
  Pop $1
  Pop $0
FunctionEnd

Section
  StrCpy $App "$EXEDIR\app\${CIDIA_EXE_APP}"
  ${IfNot} ${FileExists} "$App"
    MessageBox MB_ICONSTOP|MB_OK "No se encuentra la app de CidIA en $EXEDIR\app.$\r$\n$\r$\nVuelve a ejecutar el instalador de CidIA."
    SetErrorLevel 1
    Quit
  ${EndIf}

  ReadRegStr $Servidor HKCU "${CIDIA_CLAVE}" "Servidor"
  ${If} $Servidor == ""
    StrCpy $Servidor "${SERVIDOR}"
  ${EndIf}
  StrCpy $RutaPlugin "$EXEDIR\plugins\cidia"
  ${WordReplace} "$RutaPlugin" "\" "/" "+" $RutaPlugin

  Call Reparar
  Call PrepararRed

  ; Entorno de la app (lo heredan el proceso de Electron y su Host).
  System::Call 'kernel32::SetEnvironmentVariable(t "DSH_HOME", t "${CIDIA_DATOS}") i'
  System::Call 'kernel32::SetEnvironmentVariable(t "DSH_TELEMETRY_DISABLED", t "1") i'
  ; Un token heredado del entorno dejaría la credencial del modelo en solo lectura.
  System::Call 'kernel32::SetEnvironmentVariable(t "CIDIA_GATEWAY_TOKEN", p 0) i'

  ReadRegStr $Anterior HKCU "${CIDIA_CLAVE_PROTOCOLO}" ""
  ${GetParameters} $R0
  Exec '"$App" --user-data-dir="${CIDIA_NAVEGADOR}" $R0'

  ; Si el protocolo dsh:// era de otra app (DeepSeek Harness), se le devuelve en cuanto la app
  ; base lo registre a su nombre (lo hace al arrancar). Se vigila hasta 90 segundos.
  ClearErrors
  ${WordFind} "$Anterior" "$EXEDIR\app" "E+1{" $0
  ${If} ${Errors}
  ${AndIf} $Anterior != ""
    StrCpy $R0 "$Anterior"
    StrCpy $R1 "$EXEDIR\app"
    StrCpy $R2 ""
    ${For} $1 1 45
      Sleep 2000
      ReadRegStr $0 HKCU "${CIDIA_CLAVE_PROTOCOLO}" ""
      ${If} $0 != $Anterior
        Call RestaurarProtocolo
        ${Break}
      ${EndIf}
    ${Next}
  ${EndIf}
  ClearErrors
SectionEnd
