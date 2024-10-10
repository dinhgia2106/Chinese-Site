import tkinter as tk
from tkinter import ttk, messagebox
import math

class CardGame:
    def __init__(self, master):
        self.master = master
        self.master.title("Trò chơi bài")
        
        self.deck = ['J', 'J'] + ['Q', 'K', 'A'] * 6
        self.players = 4
        self.player_hand = []
        self.trump_card = None
        self.player_position = None
        self.first_player = None
        self.current_player = None
        
        self.setup_ui()
        
    def setup_ui(self):
        # Frame cho người chơi chính
        player_frame = ttk.LabelFrame(self.master, text="Bài của bạn")
        player_frame.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.hand_entry = ttk.Entry(player_frame, width=20)
        self.hand_entry.pack(side=tk.LEFT, padx=5)
        
        # Frame cho lá chủ
        trump_frame = ttk.LabelFrame(self.master, text="Lá chủ")
        trump_frame.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        
        self.trump_entry = ttk.Entry(trump_frame, width=5)
        self.trump_entry.pack(side=tk.LEFT, padx=5)
        
        # Frame cho vị trí của người chơi
        position_frame = ttk.LabelFrame(self.master, text="Vị trí của bạn")
        position_frame.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        
        self.position_var = tk.StringVar(value="1")
        for i in range(1, 5):
            ttk.Radiobutton(position_frame, text=f"Người {i}", variable=self.position_var, value=str(i)).pack(side=tk.LEFT)
        
        # Frame cho người đi trước
        first_player_frame = ttk.LabelFrame(self.master, text="Người đi trước")
        first_player_frame.grid(row=3, column=0, padx=10, pady=5, sticky="w")
        
        self.first_player_var = tk.StringVar(value="1")
        for i in range(1, 5):
            ttk.Radiobutton(first_player_frame, text=f"Người {i}", variable=self.first_player_var, value=str(i)).pack(side=tk.LEFT)
        
        # Nút để bắt đầu trò chơi
        start_button = ttk.Button(self.master, text="Bắt đầu trò chơi", command=self.start_game)
        start_button.grid(row=4, column=0, pady=10)
        
        # Frame cho việc nhập bài của người chơi khác
        other_player_frame = ttk.LabelFrame(self.master, text="Người chơi khác đánh")
        other_player_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=5, sticky="n")
        
        self.other_player_entry = ttk.Entry(other_player_frame, width=20)
        self.other_player_entry.pack(padx=5, pady=5)
        
        check_button = ttk.Button(other_player_frame, text="Kiểm tra", command=self.check_other_player)
        check_button.pack(pady=5)
        
        # Frame cho việc đánh bài của người chơi chính
        your_play_frame = ttk.LabelFrame(self.master, text="Bài bạn đánh")
        your_play_frame.grid(row=2, column=1, rowspan=2, padx=10, pady=5, sticky="n")
        
        self.your_play_entry = ttk.Entry(your_play_frame, width=20)
        self.your_play_entry.pack(padx=5, pady=5)
        
        play_button = ttk.Button(your_play_frame, text="Đánh bài", command=self.play_your_cards)
        play_button.pack(pady=5)
        
        # Label để hiển thị kết quả
        self.result_label = ttk.Label(self.master, text="")
        self.result_label.grid(row=5, column=0, columnspan=2, pady=10)
        
    def start_game(self):
        self.player_hand = self.hand_entry.get().upper().split()
        self.trump_card = self.trump_entry.get().upper()
        self.player_position = int(self.position_var.get())
        self.first_player = int(self.first_player_var.get())
        self.current_player = self.first_player
        
        if self.trump_card not in ['Q', 'K', 'A']:
            messagebox.showerror("Lỗi", "Lá chủ phải là Q, K hoặc A")
            return
        
        messagebox.showinfo("Thông báo", f"Trò chơi đã bắt đầu!\nLá chủ: {self.trump_card}\nVị trí của bạn: Người {self.player_position}\nNgười đi trước: Người {self.first_player}")
        self.update_game_state()
        
    def check_other_player(self):
        if not self.trump_card or not self.player_position or not self.first_player:
            messagebox.showerror("Lỗi", "Vui lòng bắt đầu trò chơi trước")
            return
        
        if self.current_player == self.player_position:
            messagebox.showerror("Lỗi", "Đến lượt bạn đánh bài")
            return
        
        played_cards = self.other_player_entry.get()
        try:
            num_played = int(played_cards)
            if num_played < 0 or num_played > 3:
                raise ValueError
        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng nhập số lượng lá bài chủ từ 0 đến 3")
            return
        
        self.calculate_probabilities(num_played)
        self.update_game_state()
        
    def play_your_cards(self):
        if not self.trump_card or not self.player_position or not self.first_player:
            messagebox.showerror("Lỗi", "Vui lòng bắt đầu trò chơi trước")
            return
        
        if self.current_player != self.player_position:
            messagebox.showerror("Lỗi", "Chưa đến lượt bạn đánh bài")
            return
        
        played_cards = self.your_play_entry.get().upper().split()
        if not all(card in self.player_hand for card in played_cards):
            messagebox.showerror("Lỗi", "Bạn không có những lá bài này trên tay")
            return
        
        if len(played_cards) > 3:
            messagebox.showerror("Lỗi", "Bạn chỉ được đánh tối đa 3 lá")
            return
        
        for card in played_cards:
            self.player_hand.remove(card)
        
        self.hand_entry.delete(0, tk.END)
        self.hand_entry.insert(0, " ".join(self.player_hand))
        
        num_trump_played = sum(1 for card in played_cards if card == self.trump_card or card == 'J')
        self.calculate_probabilities(num_trump_played)
        self.update_game_state()
        
    def calculate_probabilities(self, num_played):
        remaining_cards = self.deck.copy()
        for card in self.player_hand:
            if card in remaining_cards:
                remaining_cards.remove(card)
        
        trump_count = remaining_cards.count(self.trump_card) + remaining_cards.count('J')
        total_cards = len(remaining_cards)
        
        lie_prob = 1 - self.combination(trump_count, num_played) * self.combination(total_cards - trump_count, 5 - num_played) / self.combination(total_cards, 5)
        
        remaining_trump_count = trump_count - num_played
        trump_prob = remaining_trump_count / (total_cards - 5)
        
        result = f"Xác suất nói dối: {lie_prob:.2%}\n"
        result += f"Xác suất còn lá chủ: {trump_prob:.2%}"
        self.result_label.config(text=result)
    
    def update_game_state(self):
        self.current_player = self.current_player % 4 + 1
        if self.current_player == self.player_position:
            self.master.title(f"Trò chơi bài - Lượt của bạn (Người {self.player_position})")
        else:
            self.master.title(f"Trò chơi bài - Lượt của Người {self.current_player}")
        
        if self.current_player == self.player_position:
            self.your_play_entry.config(state='normal')
            self.other_player_entry.config(state='disabled')
        else:
            self.your_play_entry.config(state='disabled')
            self.other_player_entry.config(state='normal')
    
    def combination(self, n, k):
        if k > n:
            return 0
        return math.factorial(n) // (math.factorial(k) * math.factorial(n - k)) 

root = tk.Tk()
game = CardGame(root)
root.mainloop()