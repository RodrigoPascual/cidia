import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/fira-sans/400.css'
import '@fontsource/fira-sans/500.css'
import '@fontsource/fira-sans/600.css'
import '@fontsource/fira-sans/700.css'
import './estilos.css'
import App from './App'
import { ProveedorSesion } from './sesion'
import { ProveedorAvisos } from './ui'

createRoot(document.getElementById('raiz')!).render(
  <StrictMode>
    <ProveedorAvisos>
      <ProveedorSesion>
        <App />
      </ProveedorSesion>
    </ProveedorAvisos>
  </StrictMode>,
)
