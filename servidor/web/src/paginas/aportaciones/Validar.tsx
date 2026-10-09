import { Construction } from 'lucide-react'
import { Cabecera, Tarjeta, Vacio } from '../../ui'

// Página provisional: la sustituye la implementación del módulo.
export default function Pagina() {
  return (
    <>
      <Cabecera titulo="Validar aportaciones" subtitulo="Pendientes de tu departamento." />
      <Tarjeta><Vacio icono={<Construction />} titulo="En construcción" /></Tarjeta>
    </>
  )
}
