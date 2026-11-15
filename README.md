# Cheque Mate

**Build, automate, and debug a chaotic cheque-clearing factory before the piles expire!**

Step into the Central Clearing Facility with **$3,500** in startup capital and turn a cluttered backroom into a high-speed financial sorting floor. Haul stacks of incoming cheques, route them across conveyor networks, stamp and polish legitimate payouts, catch disguised fraud before it hits your tubes, and expand through locked facility bulkheads.

## Running Locally

```bash
python main.py
```

## Running Tests

```bash
python -m unittest discover -s tests -v
```

## Building WebAssembly

```bash
python -m pygbag --title "Cheque Mate" --template web_template.tmpl --build --archive main.py
```
