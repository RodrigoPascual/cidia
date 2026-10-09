; comun.nsh: piezas compartidas por el instalador (CidIA.nsi) y el lanzador (lanzador.nsi).
;
; Rutas de CidIA en el equipo (todas por usuario, sin permisos de administrador):
;   $LOCALAPPDATA\Programs\CidIA          instalación (app base, plugin, plantillas, lanzador)
;   $LOCALAPPDATA\CidIA\datos             DSH_HOME: perfil, capa home, .env, conversaciones
;   $LOCALAPPDATA\CidIA\navegador         datos del navegador de la app (--user-data-dir)

!include LogicLib.nsh
!include FileFunc.nsh
!include WordFunc.nsh
!include TextFunc.nsh

!define CIDIA_CLAVE "Software\CidIA"
!define CIDIA_CLAVE_DESINSTALAR "Software\Microsoft\Windows\CurrentVersion\Uninstall\CidIA"
!define CIDIA_CLAVE_PROTOCOLO "Software\Classes\dsh\shell\open\command"
!define CIDIA_EXE_APP "DeepSeek Harness.exe"
!define CIDIA_DATOS "$LOCALAPPDATA\CidIA\datos"
!define CIDIA_NAVEGADOR "$LOCALAPPDATA\CidIA\navegador"
!define CIDIA_ENLACE_PLUGIN "$LOCALAPPDATA\CidIA\datos\profiles\desktop\node_modules\cidia"

; ---------------------------------------------------------------------------------------------
; Escritura de texto en UTF-8. FileWrite de NSIS convierte a la página de códigos del sistema;
; los ficheros de configuración de la app se leen como UTF-8 (rutas con tildes, comentarios en
; castellano), así que se convierte con WideCharToMultiByte y se escribe con WriteFile sobre el
; manejador que devuelve FileOpen.
;   $R8 = manejador (FileOpen ... w)   $R9 = texto
!macro CIDIA_DEFINIR_UTF8 PREFIJO
Function ${PREFIJO}EscribirUTF8
  Push $0
  Push $1
  Push $2
  System::Call 'kernel32::WideCharToMultiByte(i 65001, i 0, w R9, i -1, p 0, i 0, p 0, p 0) i .r0'
  ${If} $0 > 1
    System::Alloc $0
    Pop $1
    System::Call 'kernel32::WideCharToMultiByte(i 65001, i 0, w R9, i -1, p r1, i r0, p 0, p 0) i .r2'
    IntOp $2 $2 - 1
    System::Call 'kernel32::WriteFile(p R8, p r1, i r2, *i 0, p 0) i .r0'
    System::Free $1
  ${EndIf}
  Pop $2
  Pop $1
  Pop $0
FunctionEnd
!macroend

; ---------------------------------------------------------------------------------------------
; Enlace del perfil al plugin (junction, no necesita permisos de administrador).
; Si ya existe un enlace se quita solo el enlace (cmd rmdir no sigue junctions); si es una
; carpeta normal se borra con su contenido.
;   $R0 = ruta del enlace
!macro CIDIA_DEFINIR_ENLACES PREFIJO
Function ${PREFIJO}QuitarEnlace
  Push $0
  System::Call 'kernel32::GetFileAttributesW(w R0) i .r0'
  ${If} $0 <> -1
    IntOp $0 $0 & 0x400 ; FILE_ATTRIBUTE_REPARSE_POINT
    ${If} $0 <> 0
      nsExec::Exec '"$SYSDIR\cmd.exe" /d /c rmdir "$R0"'
      Pop $0
    ${Else}
      RMDir /r "$R0"
    ${EndIf}
  ${EndIf}
  Pop $0
FunctionEnd

;   $R0 = ruta del enlace   $R1 = carpeta destino
Function ${PREFIJO}CrearEnlace
  Push $0
  Call ${PREFIJO}QuitarEnlace
  ${GetParent} "$R0" $0
  CreateDirectory "$0"
  nsExec::Exec '"$SYSDIR\cmd.exe" /d /c mklink /J "$R0" "$R1"'
  Pop $0
  Pop $0
FunctionEnd
!macroend

; ---------------------------------------------------------------------------------------------
; Protocolo dsh://. La app base lo registra a su nombre al arrancar (setAsDefaultProtocolClient).
; En un equipo que también tiene DeepSeek Harness, CidIA no debe quedarse con él: se restaura.
;   $R0 = valor anterior de la orden (vacío si no había)   $R1 = carpeta de la app de CidIA
;   $R2 = "borrar" para quitar el protocolo si no hay valor anterior (desinstalación)
!macro CIDIA_DEFINIR_PROTOCOLO PREFIJO
Function ${PREFIJO}RestaurarProtocolo
  Push $0
  Push $1
  ReadRegStr $0 HKCU "${CIDIA_CLAVE_PROTOCOLO}" ""
  ; ¿Apunta ahora a la app de CidIA?
  ClearErrors
  ${WordFind} "$0" "$R1" "E+1{" $1
  ${If} ${Errors}
    ; No apunta a CidIA: nada que hacer.
  ${ElseIf} "$R0" != ""
  ${AndIf} "$R0" != "$0"
    WriteRegStr HKCU "${CIDIA_CLAVE_PROTOCOLO}" "" "$R0"
  ${ElseIf} "$R0" == ""
  ${AndIf} "$R2" == "borrar"
    DeleteRegKey HKCU "Software\Classes\dsh"
  ${EndIf}
  ClearErrors
  Pop $1
  Pop $0
FunctionEnd
!macroend

; ---------------------------------------------------------------------------------------------
; ¿Está abierta la copia de la app de CidIA? Un ejecutable en uso no se puede renombrar.
;   $R0 = ruta del ejecutable   ->   $R1 = "1" si está en uso
!macro CIDIA_DEFINIR_EN_USO PREFIJO
Function ${PREFIJO}AppEnUso
  StrCpy $R1 "0"
  ${If} ${FileExists} "$R0"
    ClearErrors
    Rename "$R0" "$R0.comprobacion"
    ${If} ${Errors}
      StrCpy $R1 "1"
    ${Else}
      Rename "$R0.comprobacion" "$R0"
    ${EndIf}
  ${EndIf}
  ClearErrors
FunctionEnd
!macroend
