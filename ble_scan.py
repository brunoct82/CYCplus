import asyncio
from bleak import BleakScanner

async def main():
    print("------------------------------------------------")
    print("SCANNER BLUETOOTH (BLE)")
    print("------------------------------------------------")
    print("Procurando dispositivos... (Aguarde 5 a 10 seg)")
    print("IMPORTANTE: Feche o Zwift e desconecte do celular!")
    
    devices = await BleakScanner.discover()
    
    encontrei = False
    for d in devices:
        # Vamos imprimir tudo, mas destacar se tiver 'cycplus' ou 's3' no nome
        nome = d.name or "Desconhecido"
        endereco = d.address
        
        print(f" -> Encontrado: {nome} | Endereço: {endereco}")
        
        if "cycplus" in nome.lower() or "s3" in nome.lower() or "53530" in nome.lower():
            print(f"\n>>> ACHEI O SEU SENSOR! <<<")
            print(f"Nome: {nome}")
            print(f"Endereço MAC: {endereco}")
            print("Copie este Endereço MAC para o próximo passo.")
            encontrei = True
            print("-" * 30)

    if not encontrei:
        print("\n[DICA] Se não apareceu o Cycplus:")
        print("1. Gire o sensor para acordar.")
        print("2. Garanta que ele não está conectado no Zwift/Celular.")

# O Python precisa rodar funções async assim:
asyncio.run(main())