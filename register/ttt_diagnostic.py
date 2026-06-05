"""D.6 TTT reversibility diagnostic."""

from __future__ import annotations

import torch

from .structured import StructuredRegister


class TTTFastWeight(torch.nn.Module):
    def __init__(self, dim: int, hidden_dim: int = 2560, lr: float = 1e-2):
        super().__init__()
        self.dim = dim
        self.lr = lr
        self.encoder = torch.nn.Linear(hidden_dim, dim)
        self.fast = torch.nn.Linear(dim, dim, bias=False)

    def init_state(self, batch_size: int, device: torch.device) -> torch.Tensor:
        with torch.no_grad():
            self.fast.weight.copy_(torch.eye(self.dim, device=self.fast.weight.device))
        return torch.zeros(batch_size, self.dim, device=device)

    def push(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        target = self.encoder(branch_encoding.detach())
        h = h.detach()
        pred = self.fast(h)
        loss = ((pred - target) ** 2).mean()
        grad = torch.autograd.grad(loss, self.fast.weight, retain_graph=False)[0]
        with torch.no_grad():
            self.fast.weight -= self.lr * grad
        return (self.fast(h) + target).detach()

    def pop(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        return self.fast(h.detach() - self.encoder(branch_encoding.detach())).detach()


def run_diagnostic(dim: int = 256, hidden_dim: int = 2560, pushes: int = 5, batch_size: int = 4) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    structured = StructuredRegister(dim, hidden_dim).to(device)
    ttt = TTTFastWeight(dim, hidden_dim).to(device)
    encodings = [torch.randn(batch_size, hidden_dim, device=device) for _ in range(pushes)]
    hs0 = structured.init_state(batch_size, device)
    hs = hs0.clone()
    for i, enc in enumerate(encodings):
        hs = structured.push(hs, enc, i)
    for i in reversed(range(pushes)):
        hs = structured.pop(hs, encodings[i], i)
    ht0 = ttt.init_state(batch_size, device)
    ht = ht0.clone().requires_grad_(True)
    for i, enc in enumerate(encodings):
        ht = ttt.push(ht, enc, i)
    for i in reversed(range(pushes)):
        ht = ttt.pop(ht, encodings[i], i)
    structured_error = (hs - hs0).norm(dim=-1).mean().item()
    ttt_error = (ht - ht0).norm(dim=-1).mean().item()
    return {"structured_restore_error": structured_error, "ttt_restore_error": ttt_error, "ratio": ttt_error / max(structured_error, 1e-12)}
