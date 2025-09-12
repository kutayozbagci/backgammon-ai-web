"""
@author: ranger
"""
from algorithm2 import DRLagent2
import numpy as np
import os

class Player():
    def __init__(self, model_path=None):
        self.brain = DRLagent2()
        if model_path and os.path.exists(model_path):
            self.brain.load_model(model_path)
        
    def act(self, state, die1, die2):
        saved_state = state.copy()
        
        if die1==die2:
            dieleft = 4 
        else:
            dieleft = 2 
        
        # actions are (index, die, actiontype [0: move, -1 for collect, 1 for enter a broken])
        self.allpaths = []
        self.get_all_possibilities(state.copy(), die1, die2, dieleft, [])
        if not die1 == die2:
            self.get_all_possibilities(state.copy(), die2, die1, dieleft, [])
        
        # keep only max-length paths (must play both dice if possible)
        if self.allpaths:
            max_len = max(len(p) for p in self.allpaths)
            self.allpaths = [p for p in self.allpaths if len(p) == max_len]
            # enforce higher-die only if there exists a higher-die move
            if max_len == 1 and die1 != die2:
                hi = max(die1, die2)
                if any(p[0][1] == hi for p in self.allpaths):
                    self.allpaths = [p for p in self.allpaths if p[0][1] == hi]
        
        # dedupe by final afterstate, keeping a mapping to a representative path
        pairs = []          # list of (path, afterstate_np)
        seen = set()
        for p in self.allpaths:
            s_after_list = self.apply_path(saved_state.copy(), p)  
            s_key = tuple(s_after_list)
            if s_key not in seen:
                seen.add(s_key)
                pairs.append((p, self.flatten(s_after_list)))      
    
        if not pairs:
            return saved_state
    
        afterstates = [a for _, a in pairs]
        idx, _values = self.brain.choose(afterstates)
    
        # pick the paired path/afterstate
        chosen_path, chosen_after_np = pairs[idx]
                
        return self.apply_path(saved_state.copy(), chosen_path)
    
    def flatten(self, state):
        return np.array(state, dtype=np.float32)

    def apply_path(self, state, path):
        s = state.copy()
        for (idx, die, t) in path:
            if t == 1:
                self.enter(s, die)
            elif t == -1:
                self.collect(s, die)
            else:
                self.move_state(s, idx, die)
        return s

    # Call this after opponent finishes their move (or any reward event)
    def observe_env(self, reward=0.0):
        self.brain.on_env_reward(reward)

    # Call this every N steps to learn
    def learn(self, grad_steps=1):
        self.brain.learn(grad_steps=grad_steps)

    # Call at game end with final result (+1 win, -1 loss, 0 otherwise)
    def episode_end(self, final_reward):
        self.brain.on_episode_end(final_reward)
            
    def get_all_possibilities(self, state, die1, die2, dieleft, pathsaved):
        saved_state = state.copy()

        if dieleft > 1:
            die = die1
        else:
            die = die2
           
        # check if won
        if self.check_if_won(state):
            self.allpaths.append(pathsaved.copy())
            return
        
        # check if broken
        elif state[0] > 0:
            if self.can_enter(state, die):
                self.enter(state, die)
                pathsaved.append((3+die, die, 1))
                if dieleft > 1:
                    self.get_all_possibilities(state.copy(), die1, die2, dieleft-1, pathsaved.copy())
                else:
                    self.allpaths.append(pathsaved.copy())
            else:
                if len(pathsaved) > 0:
                    self.allpaths.append(pathsaved.copy())
                return
                    
        # check if collectable
        elif self.check_if_collectable(state):
            branched = False
        
            # Branch A — bear off (if legal)
            if self.can_collect(state, die):
                sA = state.copy()
                idx = self.collect(sA, die)
                pA = pathsaved + [(idx, die, -1)]
                if dieleft > 1:
                    self.get_all_possibilities(sA, die1, die2, dieleft-1, pA)
                else:
                    self.allpaths.append(pA.copy())
                branched = True
        
            # Branch B — move inside home 
            for a in range(22, 28):                    # home board only
                if state[a] > 0 and a + die < 28 and (state[a + die] >= -1):
                    sB = state.copy()
                    self.move_state(sB, a, die)
                    pB = pathsaved + [(a, die, 0)]
                    if dieleft > 1:
                        self.get_all_possibilities(sB, die1, die2, dieleft-1, pB)
                    else:
                        self.allpaths.append(pB.copy())
                    branched = True
        
            # if neither branch worked, close the current path if it has moves
            if not branched and len(pathsaved)>0:
                self.allpaths.append(pathsaved.copy())
            return

        # do_regular_move
        elif self.can_move_one_die(state, die):
            for a in range(4, 28):
                if state[a] > 0 and a + die < 28 and (state[a+die] >= -1):
                    next_state = saved_state.copy()
                    self.move_state(next_state, a, die)
                    next_path = pathsaved + [(a, die, 0)]
                    if dieleft > 1:
                        self.get_all_possibilities(next_state, die1, die2, dieleft-1, next_path)
                    else:
                        self.allpaths.append(next_path.copy())
            return
        else:
            if len(pathsaved) > 0:
                self.allpaths.append(pathsaved.copy())
            return
            
    def check_if_won(self, state):
        if state[1] == 15:
            return True
        return False

    def can_enter(self, state, die):
        if state[3+die] >= -1:
            return True
        return False

    def enter(self, state, die):
        if state[3+die] == -1:
            state[2] += 1
            state[3+die] += 2
        else:
            state[3+die] += 1
        state[0] -= 1
        
    def check_if_collectable(self, state):
        if state[0] != 0:
            return False
        for i in range(4, 22):
            if state[i] > 0:
                return False
        return True

    def can_collect(self, state, die):
        if self.check_if_collectable(state):
            if state[28-die]>0:
                return True
            else:
                for i in range(22, 28-die):
                    if state[i] > 0:
                        return False
            return True
        return False
    
    def collect(self, state, die):
        idx = 28 - die  # exact bear-off point
        if state[idx] > 0:
            state[idx] -= 1
            state[1] += 1
            return idx
    
        # Oversized die: remove from nearest lower point (idx+1 .. 27)
        for i in range(idx + 1, 28):
            if state[i] > 0:
                state[i] -= 1
                state[1] += 1
                return i
             
    def can_move_one_die(self, state, die):
        for a in range(4, 28):
            if state[a] > 0:
                if a + die < 28 and (state[a+die] >= -1):
                    return True
        return False
            
    def move_state(self, state, index, die):
        state[index] -= 1 
        if state[index+die] == -1:
            state[2] += 1 
            state[index+die] += 2
        else:
            state[index+die] += 1
            