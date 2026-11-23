import { Vector2 } from 'three';

export function createInput(canvas, orbit, jump, attack) {
  const keys = new Set();
  const stick = new Vector2();
  const movement = new Vector2();
  const moveKeys = [
    ['KeyA', 'ArrowLeft'], ['KeyD', 'ArrowRight'],
    ['KeyS', 'ArrowDown'], ['KeyW', 'ArrowUp'],
  ];
  const gameKeys = new Set([...moveKeys.flat(), 'ShiftLeft', 'ShiftRight', 'Space', 'KeyJ']);
  const pressed = (codes) => codes.some((code) => keys.has(code));

  window.addEventListener('keydown', (event) => {
    if (!gameKeys.has(event.code) || event.target instanceof HTMLButtonElement) return;
    event.preventDefault();
    keys.add(event.code);
    if (event.repeat) return;
    if (event.code === 'Space') jump();
    if (event.code === 'KeyJ') attack();
  });
  window.addEventListener('keyup', (event) => keys.delete(event.code));

  let drag;
  canvas.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || drag) return;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (drag?.id !== event.pointerId) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;
    drag.moved = true;
    orbit(dx, dy);
    drag.x = event.clientX;
    drag.y = event.clientY;
  });
  canvas.addEventListener('pointerup', (event) => {
    if (drag?.id !== event.pointerId) return;
    if (!drag.moved && event.pointerType === 'mouse') attack();
    drag = undefined;
  });
  canvas.addEventListener('lostpointercapture', (event) => {
    if (drag?.id === event.pointerId) drag = undefined;
  });

  const touch = document.querySelector('#touch');
  touch.hidden = navigator.maxTouchPoints === 0 && !matchMedia('(any-pointer: coarse)').matches;
  document.querySelector('#controls').hidden = !touch.hidden;
  const area = document.querySelector('#stick-area');
  const ring = document.querySelector('#stick');
  const knob = document.querySelector('#knob');
  let stickPointer;
  const origin = new Vector2();

  area.addEventListener('pointerdown', (event) => {
    if (event.pointerType === 'mouse' || stickPointer !== undefined) return;
    stickPointer = event.pointerId;
    origin.set(event.clientX, event.clientY);
    ring.style.left = `${origin.x}px`;
    ring.style.top = `${origin.y}px`;
    ring.hidden = false;
    area.setPointerCapture(stickPointer);
  });
  area.addEventListener('pointermove', (event) => {
    if (event.pointerId !== stickPointer) return;
    stick.set(event.clientX - origin.x, origin.y - event.clientY).divideScalar(40).clampLength(0, 1);
    knob.style.transform = `translate(${stick.x * 40}px, ${-stick.y * 40}px)`;
  });
  function resetStick() {
    stickPointer = undefined;
    stick.set(0, 0);
    knob.style.transform = '';
    ring.hidden = true;
  }
  area.addEventListener('lostpointercapture', (event) => {
    if (event.pointerId === stickPointer) resetStick();
  });
  document.querySelector('#jump').addEventListener('click', jump);
  document.querySelector('#attack').addEventListener('click', attack);
  window.addEventListener('blur', () => {
    keys.clear();
    drag = undefined;
    resetStick();
  });

  return {
    movement() {
      const [left, right, back, forward] = moveKeys.map(pressed);
      return movement.set(+right - +left, +forward - +back).add(stick).clampLength(0, 1);
    },
    dashing: () => pressed(['ShiftLeft', 'ShiftRight']),
  };
}
