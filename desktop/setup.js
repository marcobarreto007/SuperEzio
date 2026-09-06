document.getElementById('setup').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = document.getElementById('start');
  const status = document.getElementById('status');
  button.disabled = true; status.textContent = 'Iniciando o SuperEzio… Isso pode levar até dois minutos.';
  try { const result = await window.superEzioSetup.save(Object.fromEntries(new FormData(event.target)));
    if (!result.ok) status.textContent = result.error;
  } catch { status.textContent = 'Não foi possível iniciar. Tente novamente ou consulte os logs no menu Ajuda.'; }
  finally { button.disabled = false; }
});
