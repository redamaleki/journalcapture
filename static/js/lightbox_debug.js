function openLightbox(url) {
  if (!url) return;
  document.getElementById('lightbox-img').src = url;
  document.getElementById('lightbox').classList.add('visible');
}
