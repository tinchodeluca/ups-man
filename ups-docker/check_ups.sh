#!/bin/bash

JSON="/share/UPS/ups-docker/data/ups_status.json"
ON_BAT=$(cat $JSON | grep -o '"on_battery": true' | wc -l)
BAT_V=$(cat $JSON | grep -o '"battery_voltage": [0-9.]*' | cut -d' ' -f2)

if [ "$ON_BAT" -eq 1 ]; then
    echo "$(date): CORTE DETECTADO - Bat: ${BAT_V}V"
    
    # Enviar mail (configurar ssmtp o similar)
    # echo "Corte de luz" | mail -s "UPS Alert" tu@email.com
    
    # Si batería baja, apagar
    if (( $(echo "$BAT_V < 11.5" | bc -l) )); then
        echo "$(date): BATERIA BAJA - Apagando NAS..."
        /sbin/poweroff
    fi
fi