# SuperEzio para Windows

Aplicativo Electron com backend Python compilado e incluído. O cliente não precisa
instalar Node.js, Python ou um modelo local de linguagem.

O instalador cria atalhos no menu Iniciar e na área de trabalho. Na primeira
abertura, informe sua chave DeepSeek e as chaves opcionais de dados de mercado.
As chaves são cifradas com a proteção do Windows (Electron safeStorage), fora
da pasta de instalação. Ajuda → Abrir logs abre os dados locais do aplicativo.

Dados e configuração ficam no perfil do usuário. Desinstalar não apaga os dados
automaticamente. O backend usa loopback e uma porta livre escolhida a cada execução;
ele é encerrado junto com o aplicativo. Ordens com dinheiro real ficam bloqueadas.

## Construir

Na raiz do repositório, com Node.js, npm, Python, PyInstaller e dependências do
backend disponíveis:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_desktop.ps1
```

O script não publica na internet. Binaries Electron/NSIS são obtidos pelo mirror
configurado, respeitando o bloqueio de GitHub. O arquivo final fica em `dist/windows`.
Não são incluídos arquivos de credenciais ou dados pessoais do operador.

O instalador ainda não tem assinatura comercial Authenticode. O Windows pode
mostrar um aviso de editor desconhecido; assinatura exige certificado do publicador.

Referências de implementação: [isolamento de contexto](https://www.electronjs.org/docs/latest/tutorial/context-isolation)
e [instalador NSIS](https://www.electron.build/nsis/).
