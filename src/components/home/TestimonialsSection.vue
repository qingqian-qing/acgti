<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from '../../i18n'

const { t, tm } = useI18n()

const testimonialBase = [
  {
    name: "Benny",
    role: "ARCHITECT",
    type: "INTJ",
    color: "#8a609d",
    avatar: "linear-gradient(135deg, #f7b2b2 0%, #f3d3d3 100%)",
  },
  {
    name: "Nicole",
    role: "ADVOCATE",
    type: "INFJ",
    color: "#3ba17c",
    avatar: "linear-gradient(135deg, #b8d7ff 0%, #d6e6ff 100%)",
  },
  {
    name: "Caroline",
    role: "DEFENDER",
    type: "ISFJ",
    color: "#4298b4",
    avatar: "linear-gradient(135deg, #bdebc9 0%, #dff5e6 100%)",
  },
  {
    name: "Marta",
    role: "COMMANDER",
    type: "ENTJ",
    color: "#8a609d",
    avatar: "linear-gradient(135deg, #ffe6a8 0%, #fff1cb 100%)",
  },
]

const testimonials = computed(() =>
  testimonialBase.map((item, index) => ({
    ...item,
    quote: tm<string[]>('home.testimonials')[index] ?? '',
  })),
)
</script>

<template>
  <section class="testimonials" v-reveal>
    <div class="quote-badge">"</div>
    <div class="container">
      <p class="testimonial-tag">Testimonials</p>
      <h2 class="testimonial-title">{{ t('home.testimonialsTitle') }}</h2>

      <div class="testimonial-track">
        <article v-for="item in testimonials" :key="item.name" class="testimonial-card">
          <div class="card-top" :style="{ backgroundColor: item.color }"></div>
          <div class="card-body">
            <div class="profile-row">
              <div class="avatar" :style="{ background: item.avatar }"></div>
              <div>
                <h3>{{ item.name }}</h3>
                <p :style="{ color: item.color }">{{ item.role }} ({{ item.type }})</p>
              </div>
            </div>
            <p class="quote">{{ item.quote }}</p>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.container {
  width: min(1200px, calc(100% - 2rem));
  margin: 0 auto;
}

.testimonials {
  padding: 5.5rem 0;
  position: relative;
}

.quote-badge {
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%) rotate(12deg);
  width: 64px;
  height: 64px;
  border-radius: 16px;
  background: #e5b540;
  color: #fff;
  font-size: 3rem;
  font-family: Georgia, serif;
  line-height: 1.3;
  text-align: center;
  box-shadow: 0 10px 24px rgba(131, 96, 17, 0.28);
}

.testimonial-tag {
  text-align: center;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #e5b540;
  font-weight: 800;
  font-size: 0.75rem;
  margin: 1.6rem 0 0;
}

.testimonial-title {
  text-align: center;
  margin: 0.6rem 0 2.6rem;
  font-size: clamp(1.9rem, 4.5vw, 2.8rem);
}

.testimonial-track {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(280px, 360px);
  gap: 1.2rem;
  overflow-x: auto;
  padding: 0.4rem 0.2rem 1.2rem;
  scroll-snap-type: x mandatory;
}

.testimonial-card {
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(32, 38, 46, 0.1);
  overflow: hidden;
  scroll-snap-align: center;
}

.card-top {
  height: 6px;
}

.card-body {
  padding: 1.4rem;
}

.profile-row {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}

.avatar {
  width: 52px;
  height: 52px;
  border-radius: 999px;
}

.profile-row h3 {
  margin: 0;
  font-size: 1.05rem;
}

.profile-row p {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  font-weight: 700;
}

.quote {
  margin: 1rem 0 0;
  color: #555;
  line-height: 1.7;
  font-size: 0.95rem;
}

@media (max-width: 768px) {
  .testimonial-track {
    grid-auto-columns: minmax(260px, 86vw);
  }
}
</style>
