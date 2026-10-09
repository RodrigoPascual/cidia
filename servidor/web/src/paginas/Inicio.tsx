import { Construction } from 'lucide-react'
import { Cabecera, Tarjeta, Vacio } from '../ui'

// Página provisional: la sustituye la implementación del módulo.
export default function Pagina() {
  return (
    <>
      <Cabecera titulo="Inicio" subtitulo="Resumen de tu trabajo en CidIA." />
      <Tarjeta><Vacio icono={<Construction />} titulo="En construcción" /></Tarjeta>
    </>
  )
}
