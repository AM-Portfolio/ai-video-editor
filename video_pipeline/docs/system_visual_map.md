# 🗺️ Visual System Map: AI Video Editor

> **"Understanding the Brain in 5 Charts"**

---

## 1. The High-Level Pipeline
*How raw video becomes a polished edit.*

```mermaid
graph LR
    Input[🎥 Raw Video] --> A[Perception]
    A --> B[Understanding]
    B --> C[Decision]
    C --> D[Action]
    D --> Output[🎬 Final Edit]

    style Input fill:#333,stroke:#fff,stroke-width:2px
    style Output fill:#2ecc71,stroke:#fff,stroke-width:2px
```

---

## 2. The Decision Logic (The Brain)
*How the system decides "Keep" vs "Discard".*

```mermaid
flowchart TD
    subgraph SENSORS [Perception Layer]
        Visual[Motion Score]
        Face[Face Score]
        Speech[Speech Score]
    end

    subgraph LABELS [Semantic Layer]
        Regex[Hinglish/Keywords]
        LLM[Together AI]
    end

    subgraph BRAIN [The Decider]
        calc{Calculate Score}
    end

    Visual --> calc
    Face --> calc
    Speech --> calc
    Regex -->|Product/Funny/General| calc
    LLM -->|Fallback Tag| calc

    calc -->|Score >= 0.65| KEEP[✅ Keep]
    calc -->|Score < 0.65| DISCARD[❌ Discard]

    style KEEP fill:#27ae60,color:white
    style DISCARD fill:#c0392b,color:white
```

---

## 3. Semantic Tagging Flow (Hinglish Supported)
*How it understands what you say.*

```mermaid
sequenceDiagram
    participant Audio
    participant Regex as ⚡️ Regex
    participant LLM as 🧠 Together AI
    participant Tag as 🏷️ Final Tag

    Audio->>Regex: "Arre bhai code phat gaya"
    Regex-->>Tag: Found "bhai code" -> PRODUCT (Fast Match!)
    
    Audio->>Regex: "Just talking about life"
    Regex-->>LLM: No keyword found...
    LLM-->>Tag: Analyzed Context -> GENERAL
```

---

## 4. Execution Policy
*Where do the clips go?*

```mermaid
stateDiagram-v2
    [*] --> Scored
    Scored --> Keep: Score > 0.75
    Scored --> Quarantine: Score 0.6 - 0.75
    Scored --> Discard: Score < 0.6

    state Keep {
        Product_Folder
        Funny_Folder
    }
    state Quarantine {
        Manual_Review
    }
    state Discard {
        Trash
    }
```

---

## 5. File & Data Flow
*What files are created where?*

```mermaid
graph TD
    subgraph PROCESSING [processing/]
        V[Video Chunks]
        S[scores.json]
        T[tags.json]
        D[decisions.json]
    end

    subgraph OUTPUT [output_clips/]
        Selected[📁 selected/]
        Quarantine[📁 quarantine/]
    end

    V -->|Motion/Face/VAD| S
    V -->|Whisper/LLM| T
    S & T -->|Decider| D
    D -->|Executor| Selected & Quarantine
```
