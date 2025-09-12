import random
from collections import deque, namedtuple
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import os

Transition = namedtuple("Transition", "sa r sn done")

class ValueNet(nn.Module):
    def __init__(self, state_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 512), nn.ReLU(),
            nn.Linear(512, 256), nn.ReLU(),
            nn.Linear(256, 256), nn.ReLU(),
            nn.Linear(256, 1)
        )
    def forward(self, x):
        return self.net(x).squeeze(-1)   # shape: (B,)

class DRLagent2:
    def __init__(self, state_dim=28, gamma=0.999, lr=4e-4, 
                 buffer_size=250_000, batch_size=1024, 
                 eps_start=0.0, eps_end=0.05, eps_decay_steps=200_000,
                 target_tau=0.005, device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.gamma = gamma
        self.batch_size = batch_size
        self.buffer = deque(maxlen=buffer_size)
        self.steps = 0
        self.eps_start, self.eps_end, self.eps_decay = eps_start, eps_end, eps_decay_steps
        self.tau = target_tau

        self.net = ValueNet(state_dim).to(self.device)
        self.tgt = ValueNet(state_dim).to(self.device)
        self.tgt.load_state_dict(self.net.state_dict())
        self.opt = torch.optim.Adam(self.net.parameters(), lr=lr)

        # training stitch helpers
        self.prev_after = None   # afterstate_t waiting for next link
        self.prev_reward = 0.0   # reward accumulated since last afterstate
        
        self.loss_history = [] 
    
    def save_model(self, filepath):
        """Save the neural network weights"""
        torch.save({
            'model_state_dict': self.net.state_dict(),
            'optimizer_state_dict': self.opt.state_dict(),
        }, filepath)
        print(f"Model saved to {filepath}")
    
    def load_model(self, filepath):
        """Load the neural network weights"""
        if os.path.exists(filepath):
            checkpoint = torch.load(filepath, map_location=self.device)
            self.net.load_state_dict(checkpoint['model_state_dict'])
            self.opt.load_state_dict(checkpoint['optimizer_state_dict'])
            self.tgt.load_state_dict(self.net.state_dict())
            print(f"Model loaded from {filepath}")
        else:
            print(f"No model found at {filepath}")

    def epsilon(self):
        # linear decay
        # t = min(self.steps, self.eps_decay)
        # return self.eps_end + (self.eps_start - self.eps_end) * (1 - t / self.eps_decay)
        
        # self.eps_start = self.eps_start * 0.999
        return max(self.eps_start, 0.0)

    def choose(self, afterstates):
        """
        afterstates: list[np.ndarray] each shape (state_dim,)
        Returns: (idx, values_np)
        """
        eps = self.epsilon()
        if not afterstates:    # no move: pass
            return None, []

        if random.random() < eps:
            idx = random.randrange(len(afterstates))
            return idx, []

        with torch.no_grad():
            x = torch.tensor(np.stack(afterstates), dtype=torch.float32, device=self.device)
            v = self.net(x)  # (N,)
            idx = torch.argmax(v).item()
        return idx, v.detach().cpu().numpy().tolist()

    def remember(self, sa, r, sn, done):
        self.buffer.append(Transition(sa, r, sn, done))

    def _soft_update(self):
        with torch.no_grad():
            for p, tp in zip(self.net.parameters(), self.tgt.parameters()):
                tp.data.mul_(1 - self.tau).add_(self.tau * p.data)

    def learn(self, grad_steps=2):
        if len(self.buffer) < self.batch_size:
            return
        self.eps_start = self.eps_start * 0.99985
        running = 0.0
        for _ in range(grad_steps):
            batch = random.sample(self.buffer, self.batch_size)
            sa = torch.tensor(np.stack([b.sa for b in batch]), dtype=torch.float32, device=self.device)
            r  = torch.tensor([b.r for b in batch], dtype=torch.float32, device=self.device)
            done = torch.tensor([b.done for b in batch], dtype=torch.float32, device=self.device)
            # For sn: if done, value is 0; else evaluate target V
            nonterm = np.array([b.sn if b.sn is not None else np.zeros_like(batch[0].sa) for b in batch])
            sn = torch.tensor(nonterm, dtype=torch.float32, device=self.device)

            v_sa = self.net(sa)                       # (B,)
            with torch.no_grad():
                v_sn = self.tgt(sn)                   # (B,)
                target = r + self.gamma * (1 - done) * v_sn

            loss = F.smooth_l1_loss(v_sa, target)
            self.opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
            self.opt.step()
            self._soft_update()
            running += loss.item()
        self.loss_history.append(running / max(1, grad_steps))

    # --- stitching across turns ---
    def on_action_committed(self, afterstate):
        """
        Call this right after you choose & apply your move (the afterstate you just created).
        We *close* the previous afterstate transition here, using this new afterstate as sn.
        """
        if self.prev_after is not None:
            self.remember(self.prev_after, self.prev_reward, afterstate, False)
            self.prev_reward = 0.0
        self.prev_after = afterstate

    def on_env_reward(self, r):
        """Accumulate rewards that happen between your moves (hits, gammons, etc.)."""
        self.prev_reward += float(r)

    def on_episode_end(self, final_reward):
        """Close the last pending transition at terminal."""
        if self.prev_after is not None:
            self.remember(self.prev_after, self.prev_reward + float(final_reward), None, True)
        self.prev_after = None
        self.prev_reward = 0.0
