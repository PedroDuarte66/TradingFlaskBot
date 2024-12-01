from flask import Flask, request, jsonify
import ccxt
import config, data.saldo as saldo
import funsiones

app = Flask(__name__)

# Configurar conexión con Binance
binance = ccxt.binance({
    'apiKey': config.API_KEY,
    'secret': config.API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'test': True #Asegura que se use el modo de pruba
    }
})

# Función para calcular el saldo disponible en futuros
def get_available_balance():
    try:
        futures_balance = binance.fetch_balance({'type': 'future'})
        usdt_balance = futures_balance['total']['USDT']
        print(f"Saldo USDT disponible: {usdt_balance}")
        return usdt_balance
    except Exception as e:
        print(f"Error al obtener el saldo: {e}")
        return 0
    
#obtener el saldo de la posicion actual si hay una    
def get_position_balance(ticker):
    """
    Devuelve el saldo total de una posición abierta (long o short) para un símbolo específico.
    Si no hay posiciones abiertas, devuelve 0.
    """
    try:
        # Fetch all positions from Binance Futures
        positions = binance.fetch_positions({'symbol': ticker})
        
        # Find the specific position for the given ticker
        for position in positions:
            if position['symbol'] == ticker:
                position_size = float(position['contracts'])  # Quantity of the position
                position_margin = float(position['margin'])  # Margin used for the position
                
                if position_size > 0:  # Long position
                    print(f"Posición LONG abierta en {ticker}: {position_size}, margen: {position_margin}")
                    return position_margin  # Return total margin for the position
                elif position_size < 0:  # Short position
                    print(f"Posición SHORT abierta en {ticker}: {position_size}, margen: {position_margin}")
                    return position_margin  # Return total margin for the position
        
        # If no positions are open for this ticker
        print(f"No hay posiciones abiertas para {ticker}.")
        return 0
    except Exception as e:
        print(f"Error al obtener el saldo de la posición para {ticker}: {e}")
        return 0


    
    
# Endpoint para recibir alertas desde TradingView
@app.route('/alerta', methods=['POST'])
def alerta():
    msg = request.json
    
    # Validar claves esenciales
    required_keys = ["signal", "ticker", "price", "qty"]
    for key in required_keys:
        if key not in msg:
            return {"error": f"Falta la clave {key}"}, 400

    # Capturar los datos relevantes
    signal = msg.get("signal")
    ticker = msg.get("ticker")
    price = float(msg.get("price"))
    qty = float(msg.get("qty"))

    print(f"Accion: {signal}, Ticker: {ticker}, Precio: {price}, qty: {qty}")

    # Consultar el saldo disponible
    available_balance = get_available_balance()
    print(f"Saldo disponible en futuros: {available_balance}")

    # Monto a invertir (usa todo el saldo disponible)
    amount_to_invest = qty   #available_balance
    print(f"Monto a invertir: {amount_to_invest}")

    # Crear la orden en Binance
    try:
          # Obtener todas las posiciones abiertas
        balance = binance.fetch_balance({'type': 'future'})
        positions = balance['info']['positions']
        position = next((p for p in positions if p['symbol'] == ticker), None)

        if position:
            position_amount = float(position['positionAmt'])  # Tamaño de la posición actual
            if position_amount > 0:  # Posición LONG
                if signal == "buy":
                    print("Ya existe una posición LONG, no se requiere acción.")
                    return {"msg": "Sin cambios, posición LONG ya abierta."}
                elif signal == "sell":
                    print("Cerrando posición LONG y abriendo posición SHORT.")
                    # Cerrar posición LONG
                    binance.create_order(
                        symbol=ticker,
                        type="market",
                        side="sell",
                        amount=abs(position_amount),
                        params={"reduceOnly": True}
                    )
                    # Abrir posición SHORT
                    order = binance.create_market_sell_order(
                        symbol=ticker,
                        amount=abs(position_amount)
                    )
                    print(f"Posición SHORT abierta: {order['status']}")
            elif position_amount < 0:  # Posición SHORT
                if signal == "sell":
                    print("Ya existe una posición SHORT, no se requiere acción.")
                    return {"msg": "Sin cambios, posición SHORT ya abierta."}
                elif signal == "buy":
                    print("Cerrando posición SHORT y abriendo posición LONG.")
                    # Cerrar posición SHORT
                    binance.create_order(
                        symbol=ticker,
                        type="market",
                        side="buy",
                        amount=abs(position_amount),
                        params={"reduceOnly": True}
                    )
                    # Abrir posición LONG
                    order = binance.create_market_buy_order(
                        symbol=ticker,
                        amount=abs(position_amount)
                    )
                    print(f"Posición LONG abierta: {order['status']}")
        else:
            print("No hay posiciones abiertas.")
            # Si no hay posiciones, abrir según la señal      


        if signal == "buy":
            # Ajustar el precio reduciendo un 0.2%
            adjusted_price = price * (1 + 0.002)  # 0.2% mas
            order = binance.create_limit_buy_order(
                symbol=ticker,
                amount=amount_to_invest / adjusted_price,  # Calcular la cantidad a comprar en base al precio
                price=adjusted_price  # Precio ajustado
            )
            print(f"Orden de compra ejecutada: {order["status"]}")
        elif signal == "sell":
            # Ajustar el precio reduciendo un 0.2%
            adjusted_price = price * (1 - 0.002)  # 0.2% menos

            order = binance.create_limit_sell_order(
                symbol=ticker,
                amount=amount_to_invest / adjusted_price,  # Calcular la cantidad a vender en base al precio
                price=adjusted_price
            )
            print(f"Orden de venta ejecutada: {order["status"]}")


        elif signal == "close_long":
            try:
                # Fetch futures positions
                balance = binance.fetch_balance({'type': 'future'})  # Specify futures account
                positions = balance['info']['positions']  # Extract positions information
                # Find the position for the specified ticker
                position = next((p for p in positions if p['symbol'] == ticker), None)
        
                if position:
                    position_amount = float(position['positionAmt'])
                    if position_amount > 0:  # Ensure it's a long position
                        # Create a reduce-only market sell order
                        order = binance.create_order(
                            symbol=ticker,
                            type="market",
                            side="sell",
                            amount=abs(position_amount),  # Absolute value of position size
                            params={"reduceOnly": True}
                        )
                        print(f"Orden de cierre de posición larga ejecutada: {order['status']}")
                    else:
                        print("No hay posición larga abierta para cerrar.")
                else:
                    print(f"No se encontró ninguna posición para el símbolo {ticker}.")
            except Exception as e:
                print(f"Error al ejecutar la orden: {e}")



        elif signal == "close_short":
            try:
                # Fetch futures positions
                balance = binance.fetch_balance({'type': 'future'})  # Specify futures account
                positions = balance['info']['positions']  # Extract positions information
                # Find the position for the specified ticker
                position = next((p for p in positions if p['symbol'] == ticker), None)
        
                if position:
                    position_amount = float(position['positionAmt'])
                    if position_amount < 0:  # Ensure it's a short position
                        # Create a reduce-only market buy order
                        order = binance.create_order(
                            symbol=ticker,
                            type="market",
                            side="buy",
                            amount=abs(position_amount),  # Absolute value of position size
                            params={"reduceOnly": True}
                        )
                        print(f"Orden de cierre de posición corta ejecutada: {order['status']}")
                    else:
                        print("No hay posición corta abierta para cerrar.")
                else:
                    print(f"No se encontró ninguna posición para el símbolo {ticker}.")
            except Exception as e:
                print(f"Error al ejecutar la orden: {e}")
    except Exception as e:
        print(f"error al ejecutar la orden: {e}")
    
    return {
        'msg': msg,
    }
    
    return {
        'msg': msg,
    }

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=80, debug=True)


        #     elif signal == "close_short":
    #         # Close a short position with a reduce-only market buy order
    #         position_amount = abs(binance.fetch_position(ticker)['size'])  # Get the current position size
    #         order = binance.create_order(
    #         symbol=ticker,
    #         type="market",
    #         side="buy",
    #         amount=position_amount,
    #         params={"reduceOnly": True}  # Ensure it closes the short position only
    #     )
    #     print(f"Orden de cierre de posición corta ejecutada: {order['status']}")
    # except Exception as e:
    #     print(f"Error al ejecutar la orden: {e}")
