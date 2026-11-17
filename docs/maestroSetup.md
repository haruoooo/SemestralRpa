# Configurar o BotCity Maestro (uma vez)

Os nomes de menus podem variar um pouco conforme a versão do Maestro.

1. **Conta:** em https://developers.botcity.dev, crie a conta gratuita (**Sign up for Free**, plano Community).
2. **SDK e Runner:**
   1. No Orquestrador, clique em **Download Studio** e baixe a versão para Windows.
   2. Rode o `wizard`, faça login e conclua a instalação. A pasta padrão é `Documents\BotCity`.
   3. No Wizard, clique em **Setup Runner** → **Create a New Runner**, com o nome `foraDoPicoRunner`.
   4. Abra `Documents\BotCity\conf\conf.bcf` e confira se `server`, `login`, `key` e `machineId` estão preenchidos.
   5. Na linha `pythonBinary`, coloque o caminho do Python 3.13 com barras `/`, porque o arquivo trata `\` como caractere especial:
      ```
      pythonBinary=C:/Users/<usuário>/AppData/Local/Programs/Python/Python313/python.exe
      ```
   6. Instale no Python global o que o Runner usa para criar o ambiente do robô:
      ```
      python -m pip install --upgrade pip setuptools virtualenv
      ```
3. **Pasta de trabalho:** o Runner descompacta o robô numa pasta própria. Esta variável faz o robô usar o `.env`, o `data\` e os `logs\` do projeto:
   ```
   setx FORADOPICO_HOME "C:\caminho\do\SemestralRpa"
   ```
   Feche e abra de novo o Wizard depois desse comando, para o Runner enxergar a variável.
4. **Senhas:** no plano gratuito, o cofre de credenciais do Maestro não está disponível, e o robô lê as senhas do `.env` da pasta de trabalho. Em plano pago, crie no cofre o rótulo `foraDoPico` com as chaves `smtpUser`, `smtpPassword` e `logSalt`. Elas passam a ter prioridade sobre o `.env`.
5. **Pacote:** na pasta do projeto, rode `.\build.ps1`. Ele gera o `foraDoPicoRpa.zip`, sem o `.env`.
6. **Easy Deploy:** preencha assim:
   - automação `foraDoPicoRpa`, repositório `DEFAULT`;
   - ID do robô `foraDoPicoRpa`, com a versão;
   - tecnologia **Python**;
   - o arquivo `foraDoPicoRpa.zip`;
   - o Runner `foraDoPicoRunner`.

   Para atualizar, escolha **Escolher uma automação existente**, use um número de versão novo e marque **Liberar esta versão**.
7. **Parâmetros:**
   1. Na automação, aba **Desenvolvimento**, adicione três parâmetros do tipo texto: `flow` (obrigatório), `at` e `ignoreWindow` (opcionais).
   2. Deixe o **Label** de cada um igual ao nome. É pelo Label que o Maestro entrega o valor ao robô.
   3. Role até o fim da página e salve.
8. **Ligar o Runner:** no Wizard, clique em **Runner - GUI** e depois em **START**. Em **Runners**, ele deve aparecer como **Ativo**.
9. **Aquecimento:**
   1. Com o mock da API no ar, crie uma tarefa com `flow` = `lineMonitor`. A primeira execução demora alguns minutos, porque o Runner cria o ambiente Python e instala as dependências.
   2. O log do Runner (`Documents\BotCity\logs\log.txt`) deve mostrar "Pasta de trabalho".
10. **Agendamento (opcional):** em **Agendamentos**, crie um para cada fluxo: `scheduleImport` a cada 5 min, `agendaDispatch` a cada 10 min e `lineMonitor` a cada 5 min.
