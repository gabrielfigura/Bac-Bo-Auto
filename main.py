import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from PIL import Image
import cv2  # Para detecção de cores no histórico
import numpy as np
from telegram import Bot
from telegram.error import TelegramError
from datetime import datetime, date  # Para reset diário

# CONFIGURAÇÕES - SUBSTITUA PELOS SEUS DADOS
USERNAME = '931787918'  # Seu login Elephant Bet Angola
PASSWORD = '97713'  # Sua senha (use variáveis de ambiente para segurança!)
TELEGRAM_TOKEN = "8344261996:AAEgDWaIb7hzknPpTQMdiYKSE3hjzP0mqFc"
CHAT_ID = "-1002783091818"
APOSTA_VALOR = 1000  # Valor fixo da aposta em KZ
MIN_SALDO = 1000  # Mínimo para apostar
DAILY_MAX = 10  # Máximo 10 apostas POR DIA
LIMITE_PERDA = 3  # Pare se perda total > isso (em KZ)

# Padrões: lista de (padrão_histórico, tendência_aposta) usando emojis 🔴/🔵 diretamente
PADROES = [
    (['🔴', '🔴', '🔴', '🔵', '🔴', '🔴', '🔴'], '🔵'), 
    (['🔵', '🔵', '🔵', '🔴', '🔵', '🔵', '🔵'], '🔴'), 
    (['🔴', '🔴', '🔴', '🔴', '🔴', '🔴'], '🔴'),
    (['🔴', '🔴', '🔵', '🔵', '🔴'], '🔴'),
    (['🔵', '🔵', '🔴', '🔴', '🔵'], '🔵'),
    (['🔴', '🔵', '🔴', '🔵', '🔴', '🔵'], '🔴'),
    (['🔵', '🔴', '🔵', '🔴', '🔵', '🔴'], '🔵')
]

# Inicializa Telegram
telegram_bot = Bot(token=TELEGRAM_TOKEN)

# ID da mensagem de espera (para editar)
msg_espera_id = None

# Função para enviar notificação (com try-except para erros)
def enviar_notificacao(mensagem, message_id=None):
    try:
        if message_id:
            telegram_bot.edit_message_text(chat_id=CHAT_ID, message_id=message_id, text=mensagem)
        else:
            sent_msg = telegram_bot.send_message(chat_id=CHAT_ID, text=mensagem)
            return sent_msg.message_id
        print(f"Notificação: {mensagem}")
    except TelegramError as e:
        print(f"Erro Telegram: {e}")

# Inicializa stats
acertos = 0
erros = 0
saldo_atual = 0  # Será checado no início
historico_resultados = []  # Lista de últimos resultados (ex: ['🔴', '🔵', '🔴'])
apostas_feitas = 0  # Total geral
daily_apostas = 0  # Apostas do dia atual
ultima_data = date.today()  # Para reset diário
patrimonio_inicial = 0

# Configura Selenium
options = webdriver.ChromeOptions()
options.add_argument('--headless')  # Rode sem abrir janela (remova para debug)
driver = webdriver.Chrome(options=options)  # Assuma chromedriver no PATH

def reset_diario():
    global daily_apostas, ultima_data
    hoje = date.today()
    if hoje > ultima_data:
        daily_apostas = 0
        ultima_data = hoje
        print("Novo dia: contador de apostas resetado.")
        return True
    return False

def checar_saldo():
    global saldo_atual
    try:
        saldo_element = driver.find_element(By.CLASS_NAME, 'balance')  # Ajuste selector do saldo se necessário
        texto_saldo = saldo_element.text.replace('KZ', '').replace(' ', '').replace(',', '.').strip()
        saldo_atual = float(texto_saldo)
        return saldo_atual
    except:
        return saldo_atual  # Use o último conhecido

def atualizar_historico():
    global historico_resultados
    try:
        history_element = driver.find_element(By.CLASS_NAME, 'roadmap')  # Ajuste selector do roadmap se necessário
        history_element.screenshot('historico.png')
        
        # Carrega imagem e converte para HSV para detecção de cores
        img = cv2.imread('historico.png')
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Define ranges HSV para 🔴 (vermelho) e 🔵 (azul)
        vermelho_lower1 = np.array([0, 50, 50])
        vermelho_upper1 = np.array([10, 255, 255])
        vermelho_lower2 = np.array([170, 50, 50])
        vermelho_upper2 = np.array([180, 255, 255])
        azul_lower = np.array([100, 50, 50])
        azul_upper = np.array([130, 255, 255])
        
        # Máscara para cores
        mask_vermelho = cv2.inRange(hsv, vermelho_lower1, vermelho_upper1) | cv2.inRange(hsv, vermelho_lower2, vermelho_upper2)
        mask_azul = cv2.inRange(hsv, azul_lower, azul_upper)
        
        # Conta pixels de cada cor (assume células quadradas; crop últimas 10 colunas para histórico recente)
        height, width = img.shape[:2]
        crop_width = int(width * 0.7)  # Últimas 70% da imagem (histórico recente)
        crop = img[:, width - crop_width:]
        
        # Divide em 10 "células" horizontais (ajuste se o grid for vertical ou diferente)
        cell_width = crop_width // 10
        resultados = []
        for i in range(10):
            cell = crop[:, i * cell_width : (i + 1) * cell_width]
            if cell.size == 0:
                continue
            hsv_cell = cv2.cvtColor(cell, cv2.COLOR_BGR2HSV)
            mask_v = cv2.inRange(hsv_cell, vermelho_lower1, vermelho_upper1) | cv2.inRange(hsv_cell, vermelho_lower2, vermelho_upper2)
            mask_a = cv2.inRange(hsv_cell, azul_lower, azul_upper)
            pixels_v = cv2.countNonZero(mask_v)
            pixels_a = cv2.countNonZero(mask_a)
            if pixels_v > pixels_a:
                resultados.append('🔴')
            elif pixels_a > pixels_v:
                resultados.append('🔵')
            # Ignora se neutro (empate/cinza)
        
        historico_resultados = resultados[-10:]  # Últimos 10
        print(f"Histórico atualizado: {' '.join(historico_resultados)}")  # Para debug
        return True
    except Exception as e:
        print(f"Erro no histórico: {e}")
        return False

def checar_padrao_formado():
    if len(historico_resultados) < 5:  # Mínimo para padrões
        return None
    for padrao, tendencia in PADROES:
        if len(historico_resultados) >= len(padrao) and historico_resultados[-len(padrao):] == padrao:
            return tendencia
    return None

def checar_padrao_formando():
    # Checa parciais (ex: primeiros 3-4 itens matcham algum padrão)
    mensagens = []
    for padrao, _ in PADROES:
        for i in range(3, min(5, len(padrao))):  # Parciais de 3-4 itens
            parcial = padrao[:i]
            if len(historico_resultados) >= i and historico_resultados[-i:] == parcial:
                desc = ''.join(parcial)  # Ex: '🔴🔴🔴'
                mensagens.append(f"Padrão parcial detectado: {desc}...")
                break  # Um por padrão
    if mensagens:
        enviar_notificacao(" | ".join(mensagens))

try:
    # Passo 1: Login
    driver.get('https://www.elephantbet.co.ao')
    wait = WebDriverWait(driver, 10)
    
    username_field = wait.until(EC.presence_of_element_located((By.NAME, 'username')))  # Ajuste se o campo for diferente
    password_field = driver.find_element(By.NAME, 'password')
    username_field.send_keys(USERNAME)
    password_field.send_keys(PASSWORD)
    login_button = driver.find_element(By.XPATH, '//button[@type="submit"]')
    login_button.click()
    
    time.sleep(5)
    if 'dashboard' not in driver.current_url.lower():
        raise Exception("Falha no login!")

    # Passo 2: Navega para Bac Bo Live
    driver.get('https://www.elephantbet.co.ao/casino/live')  # Ajuste URL exata se necessário
    bac_bo_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, 'Bac Bo')))
    bac_bo_link.click()
    time.sleep(5)

    # Checa saldo inicial
    saldo_atual = checar_saldo()
    patrimonio_inicial = saldo_atual
    if saldo_atual < MIN_SALDO:
        raise Exception(f"Saldo insuficiente inicial: {saldo_atual} KZ")

    # Início com sucesso
    msg_inicio = f"Bot iniciado com sucesso! Monitorando Bac Bo...\nSaldo inicial: {saldo_atual} KZ\nLimite: {DAILY_MAX} apostas/dia"
    enviar_notificacao(msg_inicio)

    # Loop principal
    ultimo_tempo_espera = time.time()
    while (saldo_atual - patrimonio_inicial) > LIMITE_PERDA:
        # Reset diário
        if reset_diario():
            enviar_notificacao(f"Novo dia! Contador resetado. Apostas hoje: 0/{DAILY_MAX}")

        if not atualizar_historico():
            time.sleep(10)
            continue

        # Checa limite diário
        if daily_apostas >= DAILY_MAX:
            if msg_espera_id:
                enviar_notificacao("Limite diário atingido: 10 apostas hoje. Reinicia amanhã. Esperando... ⏰", msg_espera_id)
            time.sleep(300)  # Espera 5min antes de checar de novo
            continue

        # Mensagem de espera a cada 15s
        if time.time() - ultimo_tempo_espera > 15:
            msg_espera = f"ESPERANDO O PADRÃO PARA APOSTAR🔥 (Apostas hoje: {daily_apostas}/{DAILY_MAX})"
            if msg_espera_id:
                enviar_notificacao(msg_espera, msg_espera_id)
            else:
                msg_espera_id = enviar_notificacao(msg_espera)
            ultimo_tempo_espera = time.time()

        # Checa padrão parcial
        checar_padrao_formando()

        # Checa padrão completo
        tendencia = checar_padrao_formado()
        if tendencia:
            # Checa saldo antes de apostar
            saldo_atual = checar_saldo()
            if saldo_atual < MIN_SALDO:
                aviso = f"Não vai ser possível apostar porque a banca está com {saldo_atual} KZ"
                enviar_notificacao(aviso)
                break  # Para de apostar

            # Aposta!
            botao_aposta = None
            if tendencia == '🔴':
                botao_aposta = wait.until(EC.element_to_be_clickable((By.ID, 'bet-banker')))  # Ajuste ID se necessário
            else:
                botao_aposta = wait.until(EC.element_to_be_clickable((By.ID, 'bet-player')))
            botao_aposta.click()
            
            valor_input = driver.find_element(By.ID, 'bet-amount')
            valor_input.clear()
            valor_input.send_keys(str(APOSTA_VALOR))
            confirm_button = driver.find_element(By.ID, 'confirm-bet')
            confirm_button.click()

            apostas_feitas += 1
            daily_apostas += 1
            print(f"Aposta #{apostas_feitas} (dia: {daily_apostas}) em {tendencia}!")

            # Atualiza mensagem de espera para "Apostando..."
            if msg_espera_id:
                enviar_notificacao(f"APOSTANDO AGORA em {tendencia}! ⏳ (Apostas hoje: {daily_apostas}/{DAILY_MAX})", msg_espera_id)

            # Espera resultado (~60s para live)
            time.sleep(60)

            # Atualiza histórico pós-rodada
            atualizar_historico()
            ultimo_resultado = historico_resultados[-1] if historico_resultados else None

            # Checa ganho/perda
            if ultimo_resultado == tendencia:
                acertos += 1
                saldo_atual += APOSTA_VALOR  # Paga 1:1 (ajuste se tie)
                resultado = f"Mais um green✅ (aposta em {tendencia})"
            else:
                erros += 1
                saldo_atual -= APOSTA_VALOR
                resultado = f"Essa errei❌ (aposta em {tendencia})"

            # Atualiza saldo real
            saldo_atual = checar_saldo()

            # Notificação com stats
            msg = f"{resultado}\nSaldo atual: {saldo_atual} KZ\nAcertos: {acertos} | Erros: {erros} | Taxa: {acertos/(acertos+erros)*100:.1f}%\nApostas hoje: {daily_apostas}/{DAILY_MAX}"
            enviar_notificacao(msg)
            print(msg)

        else:
            time.sleep(10)  # Checa a cada 10s

except Exception as e:
    erro_msg = f"Erro no bot: {str(e)}"
    enviar_notificacao(erro_msg)
    print(erro_msg)

finally:
    # Finaliza
    if msg_espera_id:
        try:
            telegram_bot.delete_message(chat_id=CHAT_ID, message_id=msg_espera_id)
        except:
            pass
    saldo_final = checar_saldo() if 'driver' in locals() else saldo_atual
    msg_final = f"Bot finalizado.\nSaldo final: {saldo_final} KZ | Acertos: {acertos}/{apostas_feitas} | Erros: {erros}\nApostas hoje: {daily_apostas}/{DAILY_MAX}"
    enviar_notificacao(msg_final)
    if 'driver' in locals():
        driver.quit()
