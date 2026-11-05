<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <label for="budget-slider" class="budget-label">
          {{ t('restocking.budget') }}: <strong>{{ formatCurrency(budget, currentCurrency) }}</strong>
        </label>
        <input
          id="budget-slider"
          type="range"
          class="budget-slider"
          min="0"
          :max="maxBudget"
          step="100"
          v-model.number="budget"
        />
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budget') }}</div>
          <div class="stat-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.orderTotal') }}</div>
          <div class="stat-value">{{ formatCurrency(total, currentCurrency) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(remaining, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.items') }}</div>
          <div class="stat-value">{{ recommendation.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedOrder') }}</h3>
          <button class="place-order-btn" :disabled="recommendation.length === 0 || submitting" @click="placeOrder">
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>
        <div v-if="confirmation" class="order-message order-success" role="status">{{ confirmation }}</div>
        <div v-if="submitError" class="order-message order-error" role="alert">{{ submitError }}</div>
        <div v-if="recommendation.length === 0" class="empty-state">{{ t('restocking.noRecommendations') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in recommendation" :key="line.sku">
                <td><strong>{{ line.sku }}</strong></td>
                <td>{{ translateProductName(line.name) }}</td>
                <td>
                  <span :class="['badge', line.trend]">{{ t(`trends.${line.trend}`) }}</span>
                </td>
                <td>{{ line.quantity }}</td>
                <td>{{ formatCurrency(line.unit_cost, currentCurrency) }}</td>
                <td><strong>{{ formatCurrency(line.lineTotal, currentCurrency) }}</strong></td>
                <td>{{ t('restocking.days', { days: line.lead_time_days }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()
    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    const submitting = ref(false)
    const confirmation = ref('')
    const submitError = ref('')

    const candidates = computed(() => {
      return forecasts.value
        .filter(f => f.forecasted_demand > f.current_demand)
        .map(f => ({ ...f, gap: f.forecasted_demand - f.current_demand }))
        .sort((a, b) => {
          const ai = a.trend === 'increasing' ? 0 : 1
          const bi = b.trend === 'increasing' ? 0 : 1
          return ai - bi || b.gap - a.gap
        })
    })

    const maxBudget = computed(() => {
      const sum = candidates.value.reduce((s, c) => s + c.gap * c.unit_cost, 0)
      return Math.ceil(sum / 100) * 100
    })

    const recommendation = computed(() => {
      let left = budget.value
      const lines = []
      for (const c of candidates.value) {
        const qty = Math.min(c.gap, Math.floor(left / c.unit_cost))
        if (qty > 0) {
          const lineTotal = qty * c.unit_cost
          lines.push({
            sku: c.item_sku,
            name: c.item_name,
            trend: c.trend,
            quantity: qty,
            unit_cost: c.unit_cost,
            lineTotal,
            lead_time_days: c.lead_time_days
          })
          left -= lineTotal
        }
      }
      return lines
    })

    const total = computed(() => recommendation.value.reduce((s, l) => s + l.lineTotal, 0))
    const remaining = computed(() => budget.value - total.value)

    const formatDate = (dateString) => {
      const d = new Date(dateString)
      if (isNaN(d.getTime())) return dateString
      return d.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        year: 'numeric', month: 'short', day: 'numeric'
      })
    }

    const placeOrder = async () => {
      submitting.value = true
      confirmation.value = ''
      submitError.value = ''
      try {
        const order = await api.createRestockOrder({
          items: recommendation.value.map(l => ({ sku: l.sku, quantity: l.quantity })),
          budget: budget.value
        })
        confirmation.value = t('restocking.success', {
          orderNumber: order.order_number,
          days: order.lead_time_days,
          date: formatDate(order.expected_delivery)
        })
      } catch (err) {
        submitError.value = err.response?.data?.detail || err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(async () => {
      try {
        forecasts.value = await api.getDemandForecasts()
        budget.value = Math.round(maxBudget.value / 2 / 100) * 100
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    })

    return {
      t,
      currentCurrency,
      formatCurrency,
      translateProductName,
      loading,
      error,
      budget,
      maxBudget,
      recommendation,
      total,
      remaining,
      submitting,
      confirmation,
      submitError,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-label {
  display: block;
  margin-bottom: 0.75rem;
  color: #64748b;
  font-size: 0.875rem;
}

.budget-label strong {
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #3b82f6;
}

.place-order-btn {
  padding: 0.5rem 1rem;
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.order-message {
  margin: 0 1.5rem 1rem;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.order-success {
  background: #d1fae5;
  color: #065f46;
}

.order-error {
  background: #fee2e2;
  color: #991b1b;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}
</style>
