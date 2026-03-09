# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "adafruit-io",
#   "adafruit-blinka",
#   "adafruit-circuitpython-ahtx0",
#   "rpi.gpio",    
# ]
# ///
"""
Publication MQTT robuste avec reconnexion et buffering
Cours 243-413-SH, Semaine 5
"""

from Adafruit_IO import MQTTClient
import board
import adafruit_ahtx0
import time
import random

from config import ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY, PUBLISH_INTERVAL

class MQTTReconnector:
    """Gère la reconnexion MQTT avec backoff exponentiel."""
    
    MIN_DELAY = 1
    MAX_DELAY = 120
    JITTER = 0.25 # Variation aléatoire de +/- 25 %
    
    def __init__(self, client):
        self.client = client
        self.delay = self.MIN_DELAY
        self.buffer = [] # Buffer pour les données pendant la déconnexion
        self.connected = False
        
    def on_connect(self, client):
        """Callback de connexion"""
        print("Connecte à Adafruit IO!")
        self.connected = True
        self.delay = self.MIN_DELAY # Reset du délai
        self._flush_buffer()
        
    def on_disconnect(self, client):
        """Callback de déconnexion"""
        print("Déconnecte de Adafruit IO")
        self.connected = False
        self.reconnect()
    
    def reconnect(self):
        """Tentative de reconnexion avec backoff exponentiel"""
        while not self.connected:
            try:
                print(f"Tentative de reconnexion...")
                self.client.connect()
                self.client.loop_background()
                return # Succès
            except Exception as e:
                # Calculer le délai avec jitter
                actual_delay = self.delay * (1 + self.JITTER * (random.random() * 2 - 1))
                
                print(f"Échec. Prochaine tentative dans {actual_delay:.1f}s...")
                time.sleep(actual_delay)
                
                # Backoff exponentiel
                self.delay = min(self.delay * 2, self.MAX_DELAY)
    
    def buffer_data(self, feed, value):
        """Ajoute des données au buffer pendant la déconnexion."""
        self.buffer.append((feed, value, time.time()))
        print(f"  [Buffer] {feed} : {value} (total : {len(self.buffer)})")
        
        # Limiter la taille du buffer (éviter de saturer la mémoire)
        if len(self.buffer) > 100:
            self.buffer.pop(0)
            
    def _flush_buffer(self):
        """Envoie les données bufferisées après reconnexion."""
        if not self.buffer:
            return
        
        print(f"Envoi de {len(self.buffer)} message bufferisés...")
        
        while self.buffer and self.connected:
            feed, value, timestamp = self.buffer.pop(0)
            age = time.time() - timestamp
            
            # Ignorer les données trop anciennes (plus de 1 heure)
            if age > 3600:
                print(f"  [Skip] {feed} : {value} (trop ancien : {age:.0f}s)")
                continue
            
            try:
                self.client.publish(feed, value)
                print(f"  [Sent] {feed} : {value}")
                time.sleep(PUBLISH_INTERVAL)
            except Exception as e:
                # Remettre dans le buffer si échec
                self.buffer.insert(0, (feed, value, timestamp))
                print(f"  [Fail] Remis dans le buffer")
                break

class RobustSensorPublisher:
    """Publication robuste des capteurs avec gestion des erreurs."""

    def __init__(self):
        # Initialiser le capteur
        i2c = board.I2C()
        self.sensor = adafruit_ahtx0.AHTx0(i2c)
        
        # Initialiser le client MQTT
        self.client = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)
        
        # Initialiser le gestionnaire de reconnexion
        self.reconnector = MQTTReconnector(self.client)
        
        # Assigner les callbacks
        self.client.on_connect = self.reconnector.on_connect
        self.client.on_disconnect = self.reconnector.on_disconnect
        
    def connect(self):
        """Connexion initiale"""
        print("Connexion initiale à Adafruit IO...")
        self.client.connect()
        self.client.loop_background()
        self.reconnector.connected = True
        
    def publish_safe(self, feed, value):
        """Publie une valeur, bufferise si déconnecté."""
        if self.reconnector.connected:
            try:
                self.client.publish(feed, value)
                print(f"  -> {feed} : {value}")
            except Exception as e:
                print(f"  [Error] {feed} : {e}")
                self.reconnector.buffer_data(feed, value)
        else:
            self.reconnector.buffer_data(feed, value)
    
    def read_and_publish(self):
        """Lire les capteurs et publier de manière robuste."""
        try:
            temperature = round(self.sensor.temperature, 1)
            humidity = round(self.sensor.relative_humidity, 1)
            
            print(f"Lecture : {temperature}C, {humidity} %")
            
            self.publish_safe('temperature', temperature)
            time.sleep(PUBLISH_INTERVAL)
            
            self.publish_safe('humidity', humidity)
            # time.sleep(PUBLISH_INTERVAL)
            
        except Exception as e:
            print(f"Erreur lecture capteur : {e}")

def main():
    publisher = RobustSensorPublisher()
    publisher.connect()
    
    print(f"Publication robuste toutes les {PUBLISH_INTERVAL} secondes...")
    print("Appuyez sur Ctrl+C pour arrêter")
    print("-" * 50)

    try:
        while True:
            publisher.read_and_publish()
            time.sleep(PUBLISH_INTERVAL)
    except KeyboardInterrupt:
        print("\nArrêt demandé par l'utilisateur")

if __name__ == "__main__":
    main()