/* PL-03 browser shell: render session snapshots and forward commands to the server. */
(function () {
  const PIECE_SHAPES = {
    I: [
      [
        [0, 1],
        [1, 1],
        [2, 1],
        [3, 1],
      ],
      [
        [2, 0],
        [2, 1],
        [2, 2],
        [2, 3],
      ],
      [
        [0, 2],
        [1, 2],
        [2, 2],
        [3, 2],
      ],
      [
        [1, 0],
        [1, 1],
        [1, 2],
        [1, 3],
      ],
    ],
    O: [
      [
        [1, 0],
        [2, 0],
        [1, 1],
        [2, 1],
      ],
      [
        [1, 0],
        [2, 0],
        [1, 1],
        [2, 1],
      ],
      [
        [1, 0],
        [2, 0],
        [1, 1],
        [2, 1],
      ],
      [
        [1, 0],
        [2, 0],
        [1, 1],
        [2, 1],
      ],
    ],
    T: [
      [
        [1, 0],
        [0, 1],
        [1, 1],
        [2, 1],
      ],
      [
        [1, 0],
        [1, 1],
        [2, 1],
        [1, 2],
      ],
      [
        [0, 1],
        [1, 1],
        [2, 1],
        [1, 2],
      ],
      [
        [1, 0],
        [0, 1],
        [1, 1],
        [1, 2],
      ],
    ],
    S: [
      [
        [1, 0],
        [2, 0],
        [0, 1],
        [1, 1],
      ],
      [
        [1, 0],
        [1, 1],
        [2, 1],
        [2, 2],
      ],
      [
        [1, 1],
        [2, 1],
        [0, 2],
        [1, 2],
      ],
      [
        [0, 0],
        [0, 1],
        [1, 1],
        [1, 2],
      ],
    ],
    Z: [
      [
        [0, 0],
        [1, 0],
        [1, 1],
        [2, 1],
      ],
      [
        [2, 0],
        [1, 1],
        [2, 1],
        [1, 2],
      ],
      [
        [0, 1],
        [1, 1],
        [1, 2],
        [2, 2],
      ],
      [
        [1, 0],
        [0, 1],
        [1, 1],
        [0, 2],
      ],
    ],
    J: [
      [
        [0, 0],
        [0, 1],
        [1, 1],
        [2, 1],
      ],
      [
        [1, 0],
        [2, 0],
        [1, 1],
        [1, 2],
      ],
      [
        [0, 1],
        [1, 1],
        [2, 1],
        [2, 2],
      ],
      [
        [1, 0],
        [1, 1],
        [0, 2],
        [1, 2],
      ],
    ],
    L: [
      [
        [2, 0],
        [0, 1],
        [1, 1],
        [2, 1],
      ],
      [
        [1, 0],
        [1, 1],
        [1, 2],
        [2, 2],
      ],
      [
        [0, 1],
        [1, 1],
        [2, 1],
        [0, 2],
      ],
      [
        [0, 0],
        [1, 0],
        [1, 1],
        [1, 2],
      ],
    ],
  };

  const PIECE_LABELS = {
    I: "Line",
    O: "Square",
    T: "Tee",
    S: "Skew",
    Z: "Zag",
    J: "Jay",
    L: "Ell",
  };

  const app = document.getElementById("tetris-app");
  if (!app) {
    return;
  }

  const boardEl = document.getElementById("tetris-board");
  const statusEl = document.getElementById("tetris-status");
  const scoreEl = document.getElementById("tetris-score");
  const linesEl = document.getElementById("tetris-lines");
  const levelEl = document.getElementById("tetris-level");
  const ticksEl = document.getElementById("tetris-ticks");
  const queueEl = document.getElementById("tetris-next-queue");
  const controlsEl = document.getElementById("tetris-controls");
  const endpoints = {
    session: app.dataset.sessionEndpoint,
    move: app.dataset.commandMove,
    rotate: app.dataset.commandRotate,
    tick: app.dataset.commandTick,
    restart: app.dataset.commandRestart,
  };

  let requestChain = Promise.resolve();
  let loopHandle = 0;

  /** Queue one request at a time so command responses render in order. */
  function enqueue(task) {
    const result = requestChain.then(task);
    requestChain = result.catch(() => undefined);
    return result;
  }

  /** Fetch a JSON payload from the Tetris runtime seam. */
  async function fetchSession(url, init) {
    const response = await fetch(url, init);
    if (!response.ok) {
      throw new Error(`Tetris request failed: ${response.status}`);
    }
    return response.json();
  }

  /** Render the authoritative snapshot into the board and HUD. */
  function renderSnapshot(snapshot) {
    app.dataset.sessionStatus = snapshot.status;
    statusEl.textContent = snapshot.status;
    scoreEl.textContent = String(snapshot.score.score);
    linesEl.textContent = String(snapshot.score.lines_cleared);
    levelEl.textContent = String(snapshot.score.level);
    ticksEl.textContent = String(snapshot.tick_count);
    renderQueue(snapshot.next_piece_queue);
    renderBoard(snapshot.board, snapshot.active_piece);
  }

  /** Render a command or sync failure without taking over game logic. */
  function reportError(error) {
    statusEl.textContent = "error";
    app.dataset.sessionStatus = "error";
    console.error(error);
  }

  /** Render the next-piece queue as a compact HUD list. */
  function renderQueue(queue) {
    queueEl.replaceChildren();
    if (!queue.length) {
      const emptyItem = document.createElement("li");
      emptyItem.textContent = "Waiting";
      queueEl.append(emptyItem);
      return;
    }

    queue.forEach((piece, index) => {
      const item = document.createElement("li");
      item.dataset.piece = piece;
      item.textContent = `${index + 1}. ${PIECE_LABELS[piece] ?? piece}`;
      queueEl.append(item);
    });
  }

  /** Render locked cells and the active piece from the current snapshot. */
  function renderBoard(board, activePiece) {
    const fragment = document.createDocumentFragment();
    const height = board.length;
    const width = height > 0 ? board[0].length : 0;
    const activeCells = activePiece ? pieceCells(activePiece) : [];
    const activePositions = new Map(activeCells.map((cell) => [`${cell.x},${cell.y}`, true]));

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const cell = document.createElement("div");
        const lockedPiece = board[y][x];
        const activeKey = `${x},${y}`;
        cell.className = "tetris-board__cell";
        cell.style.gridColumnStart = String(x + 1);
        cell.style.gridRowStart = String(y + 1);

        if (lockedPiece) {
          cell.dataset.piece = lockedPiece;
          cell.classList.add("is-locked");
        } else {
          cell.classList.add("is-empty");
        }

        if (activePositions.has(activeKey)) {
          cell.dataset.piece = activePiece.kind;
          cell.classList.add("is-active");
        }

        fragment.append(cell);
      }
    }

    boardEl.replaceChildren(fragment);
  }

  /** Convert the active-piece snapshot into absolute board cells for display. */
  function pieceCells(piece) {
    const orientations = PIECE_SHAPES[piece.kind] ?? [];
    const cells = orientations[piece.rotation % orientations.length] ?? [];
    const originX = piece.position.x;
    const originY = piece.position.y;
    return cells.map(([dx, dy]) => ({
      x: originX + dx,
      y: originY + dy,
    }));
  }

  /** Refresh the session snapshot and keep the gravity loop aligned to it. */
  async function syncSession() {
    const snapshot = await enqueue(() => fetchSession(endpoints.session));
    renderSnapshot(snapshot);
    scheduleLoop(snapshot);
    return snapshot;
  }

  /** Submit a movement or rotation command through the route seam. */
  async function submitCommand(url, body) {
    const snapshot = await enqueue(() =>
      fetchSession(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: body ? JSON.stringify(body) : undefined,
      }),
    );
    renderSnapshot(snapshot);
    scheduleLoop(snapshot);
    return snapshot;
  }

  /** Restart the authoritative session without owning any gameplay state locally. */
  async function restartSession() {
    const snapshot = await enqueue(() =>
      fetchSession(endpoints.restart, {
        method: "POST",
      }),
    );
    renderSnapshot(snapshot);
    scheduleLoop(snapshot);
    return snapshot;
  }

  /** Post the gravity tick to the server when the session is still active. */
  function scheduleLoop(snapshot) {
    if (loopHandle) {
      window.clearTimeout(loopHandle);
      loopHandle = 0;
    }
    if (snapshot.status !== "active") {
      return;
    }

    loopHandle = window.setTimeout(() => {
      submitCommand(endpoints.tick).catch(reportError);
    }, 650);
  }

  /** Wire button clicks to the server-backed command endpoints. */
  function bindControls() {
    controlsEl.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLButtonElement)) {
        return;
      }

      const command = target.dataset.command;
      if (!command) {
        return;
      }

      event.preventDefault();
      if (command === "move-left") {
        submitCommand(endpoints.move, { dx: -1, dy: 0 }).catch(reportError);
        return;
      }
      if (command === "move-right") {
        submitCommand(endpoints.move, { dx: 1, dy: 0 }).catch(reportError);
        return;
      }
      if (command === "soft-drop") {
        submitCommand(endpoints.move, { dx: 0, dy: 1 }).catch(reportError);
        return;
      }
      if (command === "rotate") {
        submitCommand(endpoints.rotate, { clockwise: true }).catch(reportError);
        return;
      }
      if (command === "new-game") {
        restartSession().catch(reportError);
      }
    });
  }

  /** Map keyboard input to the same route-backed command surface as the HUD. */
  function bindKeyboard() {
    window.addEventListener("keydown", (event) => {
      if (event.altKey || event.ctrlKey || event.metaKey) {
        return;
      }

      switch (event.key) {
        case "ArrowLeft":
          event.preventDefault();
          submitCommand(endpoints.move, { dx: -1, dy: 0 }).catch(reportError);
          break;
        case "ArrowRight":
          event.preventDefault();
          submitCommand(endpoints.move, { dx: 1, dy: 0 }).catch(reportError);
          break;
        case "ArrowDown":
          event.preventDefault();
          submitCommand(endpoints.move, { dx: 0, dy: 1 }).catch(reportError);
          break;
        case "ArrowUp":
        case "x":
        case "X":
          event.preventDefault();
          submitCommand(endpoints.rotate, { clockwise: true }).catch(reportError);
          break;
        case "Enter":
          event.preventDefault();
          restartSession().catch(reportError);
          break;
        default:
          break;
      }
    });
  }

  /** Bootstrap the browser shell on page load. */
  function boot() {
    bindControls();
    bindKeyboard();
    syncSession().catch((error) => {
      statusEl.textContent = "error";
      app.dataset.sessionStatus = "error";
      console.error(error);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
