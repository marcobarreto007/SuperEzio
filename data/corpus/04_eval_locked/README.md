# EVAL LOCKED — NUNCA USE PARA TREINO

Estes casos existem exclusivamente para medir a qualidade do modelo após fine-tuning.

Regras:
- Nunca incluir estes exemplos no dataset de treino (SFT, DPO, Critic)
- Nunca mostrar ao modelo durante o treino
- Nunca usar como exemplos few-shot no prompt
- Rodar apenas após o treino concluído, como teste cego

Se o modelo vir estes casos antes do eval, a métrica não vale nada.
