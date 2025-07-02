import random
import threading
import time

class MockExchangeService:
    def __init__(self):
        self.coins = {
            'BTC/USD': 30000.0,
            'ETH/USD': 2000.0,
            'SOL/USD': 150.0,
            'DOGE/USD': 0.15,
            'BNB/USD': 250.0
        }
        self.lock = threading.Lock()
        self.running = True
        self.update_thread = threading.Thread(target=self._update_prices, daemon=True)
        self.update_thread.start()

    def _update_prices(self):
        while self.running:
            with self.lock:
                for symbol in self.coins:
                    # Simulate price change: random walk
                    change = random.uniform(-0.5, 0.5) * self.coins[symbol] * 0.01
                    self.coins[symbol] = max(0.01, self.coins[symbol] + change)
            time.sleep(2)  # Update every 2 seconds

    def get_prices(self):
        with self.lock:
            return self.coins.copy()

    def stop(self):
        self.running = False
        self.update_thread.join()

# Global instance
mock_exchange = MockExchangeService() 