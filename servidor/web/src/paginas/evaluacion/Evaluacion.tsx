import { Construction } from 'lucide-react'
import { Cabecera, Tarjeta, Vacio } from '../../ui'

// Página provisional: la sustituye la implementación del módulo.
export default function Pagina() {
  return (
    <>
      <Cabecera titulo="Evaluación" subtitulo="Cuestionarios y observaciones." />
      <Tarjeta><Vacio icono={<Construction />} titulo="En construcción" /></Tarjeta>
    </>
  )
}
