#Requires -Version 5.1
<#
.SYNOPSIS
  ¿Es el icono principal de un ejecutable (su primer grupo de iconos, el que usan Windows y
  Electron para las ventanas) exactamente el de un .ico? Compara imagen a imagen (sha256).
  Código de salida 0 si coincide, 1 si no.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File app\instalador\icono-exe.ps1 -Exe "...\app\CidIA.exe" -Ico app\marca\cidia.ico
#>
[CmdletBinding()]
param([Parameter(Mandatory)] [string]$Exe, [Parameter(Mandatory)] [string]$Ico)
$ErrorActionPreference = 'Stop'
if (-not ('CidiaIconoExe' -as [type])) {
  Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
public static class CidiaIconoExe {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern IntPtr LoadLibraryEx(string f, IntPtr h, uint flags);
  [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr h);
  delegate bool EnumNames(IntPtr h, IntPtr tipo, IntPtr nombre, IntPtr l);
  [DllImport("kernel32.dll")] static extern bool EnumResourceNames(IntPtr h, IntPtr tipo, EnumNames f, IntPtr l);
  [DllImport("kernel32.dll")] static extern IntPtr FindResource(IntPtr h, IntPtr nombre, IntPtr tipo);
  [DllImport("kernel32.dll")] static extern IntPtr LoadResource(IntPtr h, IntPtr r);
  [DllImport("kernel32.dll")] static extern IntPtr LockResource(IntPtr r);
  [DllImport("kernel32.dll")] static extern uint SizeofResource(IntPtr h, IntPtr r);
  static byte[] Recurso(IntPtr h, IntPtr nombre, int tipo) {
    IntPtr r = FindResource(h, nombre, (IntPtr)tipo);
    if (r == IntPtr.Zero) return null;
    uint n = SizeofResource(h, r);
    byte[] b = new byte[n];
    Marshal.Copy(LockResource(LoadResource(h, r)), b, 0, (int)n);
    return b;
  }
  static string Sha(byte[] b, int o, int n) {
    using (var s = SHA256.Create()) return BitConverter.ToString(s.ComputeHash(b, o, n)).Replace("-", "");
  }
  // Huellas de las imágenes del primer grupo de iconos del ejecutable.
  public static List<string> DelExe(string ruta) {
    IntPtr h = LoadLibraryEx(ruta, IntPtr.Zero, 0x2 | 0x20); // AS_DATAFILE | AS_IMAGE_RESOURCE
    if (h == IntPtr.Zero) throw new Exception("no se puede abrir " + ruta);
    try {
      IntPtr primero = IntPtr.Zero; bool hay = false;
      EnumResourceNames(h, (IntPtr)14, (m, t, n, l) => { primero = n; hay = true; return false; }, IntPtr.Zero);
      if (!hay) throw new Exception("sin grupo de iconos");
      byte[] g = Recurso(h, primero, 14);
      int cuenta = BitConverter.ToUInt16(g, 4);
      var lista = new List<string>();
      for (int i = 0; i < cuenta; i++) {
        int id = BitConverter.ToUInt16(g, 6 + 14 * i + 12);
        byte[] img = Recurso(h, (IntPtr)id, 3);
        lista.Add(img == null ? "falta-" + id : Sha(img, 0, img.Length));
      }
      lista.Sort();
      return lista;
    } finally { FreeLibrary(h); }
  }
  public static List<string> DelIco(string ruta) {
    byte[] b = File.ReadAllBytes(ruta);
    int cuenta = BitConverter.ToUInt16(b, 4);
    var lista = new List<string>();
    for (int i = 0; i < cuenta; i++) {
      int n = BitConverter.ToInt32(b, 6 + 16 * i + 8), o = BitConverter.ToInt32(b, 6 + 16 * i + 12);
      lista.Add(Sha(b, o, n));
    }
    lista.Sort();
    return lista;
  }
}
'@
}
$deExe = [CidiaIconoExe]::DelExe((Resolve-Path $Exe).Path)
$deIco = [CidiaIconoExe]::DelIco((Resolve-Path $Ico).Path)
$igual = ($deExe -join ',') -eq ($deIco -join ',')
Write-Host ("Icono de {0}: {1} imágenes; {2}" -f (Split-Path $Exe -Leaf), $deExe.Count, $(if ($igual) { "es $(Split-Path $Ico -Leaf)" } else { "NO es $(Split-Path $Ico -Leaf) ($($deIco.Count) imágenes)" }))
exit $(if ($igual) { 0 } else { 1 })
