(ns app.views.cn.simulator
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            ["recharts" :refer [ResponsiveContainer LineChart Line XAxis YAxis
                                CartesianGrid Tooltip ReferenceLine ReferenceDot]]
            [app.api.endpoints :as ep]
            [app.views.cn.calc :as calc]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; CN simulator. The local preview mirrors backend/app/modules/commissions/simulator.py
;; so the form, result card, and curve stay responsive while the API call confirms it.

(def ^:private rc-responsive (r/adapt-react-class ResponsiveContainer))
(def ^:private rc-line-chart (r/adapt-react-class LineChart))
(def ^:private rc-line (r/adapt-react-class Line))
(def ^:private rc-x-axis (r/adapt-react-class XAxis))
(def ^:private rc-y-axis (r/adapt-react-class YAxis))
(def ^:private rc-cartesian-grid (r/adapt-react-class CartesianGrid))
(def ^:private rc-tooltip (r/adapt-react-class Tooltip))
(def ^:private rc-reference-line (r/adapt-react-class ReferenceLine))
(def ^:private rc-reference-dot (r/adapt-react-class ReferenceDot))

;; Events

(rf/reg-event-fx
 :cn/simulate
 (fn [{:keys [db]} [_ payload]]
   {:db   (-> db
              (assoc-in [:cn :simulator :simulating?] true)
              (assoc-in [:cn :simulator :error] nil)
              (assoc-in [:cn :simulator :result] nil))
    :http {:method     :post
           :url        ep/cn-simulate
           :body       payload
           :on-success [:cn/simulate-result]
           :on-failure [:cn/simulate-error]}}))

(rf/reg-event-db
 :cn/simulate-result
 (fn [db [_ response]]
   (-> db
       (assoc-in [:cn :simulator :result] (:data response))
       (assoc-in [:cn :simulator :simulating?] false)
       (assoc-in [:cn :simulator :error] nil))))

(rf/reg-event-db
 :cn/simulate-error
 (fn [db [_ response]]
   (-> db
       (assoc-in [:cn :simulator :result] nil)
       (assoc-in [:cn :simulator :simulating?] false)
       (assoc-in [:cn :simulator :error]
                 (or (get-in response [:error :message])
                     "Nao foi possivel confirmar a simulacao agora.")))))

(rf/reg-event-db
 :cn/simulator-clear
 (fn [db _]
   (-> db
       (assoc-in [:cn :simulator :result] nil)
       (assoc-in [:cn :simulator :simulating?] false)
       (assoc-in [:cn :simulator :error] nil))))

;; Subs

(rf/reg-sub
 :cn/simulator-result
 (fn [db _] (get-in db [:cn :simulator :result])))

(rf/reg-sub
 :cn/simulator-simulating?
 (fn [db _] (get-in db [:cn :simulator :simulating?])))

(rf/reg-sub
 :cn/simulator-error
 (fn [db _] (get-in db [:cn :simulator :error])))

;; Helpers

(def ^:private curve-data
  [{:score 0   :mult 0.0 :label "0%"}
   {:score 20  :mult 0.0 :label "20%"}
   {:score 20  :mult 0.2 :label "20%"}
   {:score 40  :mult 0.2 :label "40%"}
   {:score 40  :mult 0.4 :label "40%"}
   {:score 60  :mult 0.6 :label "60%"}
   {:score 80  :mult 0.8 :label "80%"}
   {:score 100 :mult 1.0 :label "100%"}
   {:score 100 :mult 1.2 :label "100%"}
   {:score 110 :mult 1.2 :label "110%"}
   {:score 110 :mult 1.8 :label "110%"}
   {:score 140 :mult 1.8 :label "140%"}
   {:score 140 :mult 2.1 :label "140%+"}
   {:score 160 :mult 2.1 :label "160%"}])

(defn- fmt-dec [v digits]
  (let [s (.toFixed (or v 0) digits)
        cleaned (if (str/includes? s ".")
                  (-> s
                      (str/replace #"0+$" "")
                      (str/replace #"\.$" ""))
                  s)]
    (str/replace cleaned "." ",")))

(defn- fmt-pct [ratio]
  (str (fmt-dec (* 100 (or ratio 0)) 0) "%"))

(defn- fmt-mult [v]
  (str (fmt-dec (or v 0) 2) "x"))

(defn- fmt-int [v]
  (.toLocaleString (js/Math.round (or v 0)) "pt-BR"))

(defn- brl [v]
  (str "R$ " (.toLocaleString (or v 0)
                              "pt-BR"
                              #js {:minimumFractionDigits 2
                                   :maximumFractionDigits 2})))

(defn- profile-from [user form]
  (if (= (:role user) "CN")
    {:nivel (:nivel user)
     :porte (:porte user)}
    {:nivel (or (:nivel form) "CN1")
     :porte (or (:porte form) "M")}))

(defn- enrich-form [user form]
  (let [{:keys [nivel porte]} (profile-from user form)
        sao-meta (or (calc/->num (:sao_meta form)) 0)
        vidas-meta (or (calc/vidas-meta-from-sao sao-meta porte) 0)]
    (assoc form
           :nivel nivel
           :porte porte
           :vidas_meta vidas-meta)))

(defn- validation-errors [form]
  (let [sao-meta (calc/->num (:sao_meta form))
        sao-realizado (calc/->num (:sao_realizado form))
        vidas-meta (calc/->num (:vidas_meta form))
        vidas-realizado (calc/->num (:vidas_realizado form))]
    (cond-> {}
      (not (pos? (or sao-meta 0)))
      (assoc :sao_meta "Informe uma meta maior que zero.")
      (neg? (or sao-realizado 0))
      (assoc :sao_realizado "Use zero ou um valor positivo.")
      (not (contains? calc/porte-factors (:porte form)))
      (assoc :porte "Cadastre o porte do CN para calcular a meta de vidas.")
      (not (contains? calc/cn-bases (:nivel form)))
      (assoc :nivel "Cadastre o nivel do CN para calcular a comissao.")
      (not (pos? (or vidas-meta 0)))
      (assoc :vidas_meta "Meta de vidas automatica indisponivel.")
      (neg? (or vidas-realizado 0))
      (assoc :vidas_realizado "Use zero ou um valor positivo."))))

(defn- field [{:keys [label value placeholder help error on-change min step disabled]}]
  [:div.field
   [:label.field-label label]
   [:input.field-input
    (cond-> {:type "number"
             :input-mode "decimal"
             :value (or value "")
             :placeholder placeholder
             :min (or min "0")
             :step (or step "1")
             :aria-invalid (boolean error)
             :disabled disabled
             :on-change #(when on-change (on-change (.. % -target -value)))}
      error (assoc :class "field-input is-invalid"))]
   (if error
     [:span.field-error error]
     (when help [:span.field-help help]))])

(defn- select-field [{:keys [label value options on-change help error disabled]}]
  [:div.field
   [:label.field-label label]
   [:select.field-input.field-select
    (cond-> {:value value
             :disabled disabled
             :on-change #(when on-change (on-change (.. % -target -value)))}
      error (assoc :class "field-input field-select is-invalid"))
    (for [{:keys [value label]} options]
      ^{:key value} [:option {:value value} label])]
   (if error
     [:span.field-error error]
     (when help [:span.field-help help]))])

(defn- computed-field [{:keys [label value help error]}]
  [:div.field
   [:label.field-label label]
   [:div.computed-field {:class (when error "is-invalid")}
    (if (some? value) value "·")]
   (if error
     [:span.field-error error]
     (when help [:span.field-help help]))])

(defn- status-badge [{:keys [simulating? confirmed?]}]
  [:span.score-badge
   (cond
     simulating? "confirmando"
     confirmed? "confirmado"
     :else "previa")])

(defn- score-card [{:keys [preview confirmed simulating?]}]
  (let [result (or confirmed preview)]
    [:div.score-card
     [:div.score-card-head
      [:span "resultado mensal"]
      [status-badge {:simulating? simulating? :confirmed? (some? confirmed)}]]
     [:div.score-row
      [:span "% SAO"]
      [:strong (fmt-pct (:pct_sao result))]]
     [:div.score-row
      [:span "% Vidas"]
      [:strong (fmt-pct (:pct_vidas result))]]
     [:div.score-row
      [:span "Score final"]
      [:strong (fmt-pct (:score_final result))]]
     [:div.score-row
      [:span "Multiplicador"]
      [:strong.accent (fmt-mult (:multiplicador result))]]
     [:div.score-final
      [:span "Comissao estimada"]
      [:strong [:span.currency "R$"] (fmt-int (:commission_amount result))]]
     [:div.score-base
      "Base mensal "
      [:strong (brl (:base preview))]
      " x multiplicador"]]))

(defn- curve-tooltip-render [props]
  (let [p (js->clj props :keywordize-keys true)
        payload (first (:payload p))
        row (when payload (:payload payload))
        row (cond-> row (and row (not (map? row))) (js->clj :keywordize-keys true))]
    (when (and (:active p) row)
      (r/as-element
       [:div.cn-recharts-tooltip
        [:span (str "score " (:label row))]
        [:strong (fmt-mult (:mult row))]]))))

(def ^:private curve-tooltip-content
  (r/reactify-component curve-tooltip-render))

(defn- multiplier-curve [result]
  (let [score-pct (* 100 (:score_final result))
        chart-score (max 0 (min 160 score-pct))
        mult (:multiplicador result)]
    [:div.cn-curve-frame
     {:role "img"
      :aria-label "Curva da regua mensal de comissao CN por score final"}
     [rc-responsive {:width "100%" :height "100%"}
      [rc-line-chart {:data (clj->js curve-data)
                      :margin #js {:top 26 :right 30 :bottom 8 :left 0}}
       [rc-cartesian-grid {:stroke "var(--border-subtle)"
                           :strokeDasharray "0"
                           :vertical false}]
       [rc-x-axis {:dataKey "score"
                   :type "number"
                   :domain #js [0 160]
                   :ticks #js [0 20 40 60 80 100 110 140 160]
                   :tickFormatter #(if (= % 160) "140%+" (str % "%"))
                   :axisLine false
                   :tickLine false
                   :tickMargin 12
                   :tick #js {:fill "var(--fg-3)"
                              :fontSize 12
                              :fontFamily "Manrope, sans-serif"}}]
       [rc-y-axis {:domain #js [0 2.1]
                   :ticks #js [0 0.5 1 1.5 2.1]
                   :tickFormatter fmt-mult
                   :axisLine false
                   :tickLine false
                   :width 56
                   :tickMargin 8
                   :tick #js {:fill "var(--fg-3)"
                              :fontSize 12
                              :fontFamily "Manrope, sans-serif"}}]
       [rc-tooltip {:cursor #js {:stroke "var(--fg-2)"
                                 :strokeWidth 1
                                 :strokeDasharray "3 4"
                                 :strokeOpacity 0.45}
                    :content curve-tooltip-content
                    :wrapperStyle #js {:outline "none"}}]
       [rc-reference-line {:x chart-score
                           :stroke "var(--cyan)"
                           :strokeWidth 1.5
                           :strokeDasharray "3 4"
                           :ifOverflow "extendDomain"}]
       [rc-line {:type "linear"
                 :dataKey "mult"
                 :name "multiplicador"
                 :stroke "var(--black)"
                 :strokeWidth 2.5
                 :dot false
                 :activeDot #js {:r 4 :fill "var(--black)"}
                 :isAnimationActive false}]
       [rc-reference-dot {:x chart-score
                          :y mult
                          :r 6
                          :fill "var(--cyan)"
                          :stroke "var(--bg-1)"
                          :strokeWidth 2
                          :ifOverflow "visible"}]]]]))

(defn page []
  (let [initial-form {:nivel "CN1"
                      :porte "M"
                      :sao_meta ""
                      :sao_realizado ""
                      :vidas_realizado "2180"}
        form (r/atom initial-form)]
    (fn []
      (let [user @(rf/subscribe [:auth/current-user])
            route @(rf/subscribe [:current-route-name])
            effective-form (enrich-form user @form)
            cn-user? (= (:role user) "CN")
            vidas-meta (:vidas_meta effective-form)
            errors (validation-errors effective-form)
            preview (calc/calculate effective-form)
            chart-result preview]
        [layout/page-shell
         {:current-route route
          :user user
          :crumbs ["plataforma rv" "cn" "simulador"]
          :title "Simulador de comissao"
          :subtitle "previa automatica conforme os campos sao preenchidos"
          :header-actions
          [[:button.btn.btn-secondary
            {:type "button"
             :on-click #(do
                          (reset! form initial-form)
                          (rf/dispatch [:cn/simulator-clear]))}
            "Resetar"]]}

         [:div.sim-grid
          [:div.card
           [:div.card-head
            [:div
             [:h3 "Parametros"]
             [:div.card-sub "Meta e realizado do periodo, com perfil do CN aplicado automaticamente"]]]
           [:div.sim-form
            (if cn-user?
              [:div.sim-profile
               [:div
                [:span "nivel"]
                [:strong (or (:nivel effective-form) "sem cadastro")]]
               [:div
                [:span "porte"]
                [:strong (or (:porte effective-form) "sem cadastro")]]]
              [:div.form-grid.-tight
               [select-field
                {:label "Nivel do CN"
                 :value (:nivel effective-form)
                 :help "define a base mensal da comissao"
                 :error (:nivel errors)
                 :options [{:value "CN1" :label "CN1, base R$ 2.000"}
                           {:value "CN2" :label "CN2, base R$ 2.500"}
                           {:value "CN3" :label "CN3, base R$ 3.000"}]
                 :on-change #(swap! form assoc :nivel %)}]
               [select-field
                {:label "Porte"
                 :value (:porte effective-form)
                 :help "define a meta automatica de vidas"
                 :error (:porte errors)
                 :options [{:value "M" :label "M, SAO x 375"}
                           {:value "G+" :label "G+, SAO x 2000"}]
                 :on-change #(swap! form assoc :porte %)}]])
            [:div.form-grid.-tight
             [field {:label "Meta SAO"
                     :value (:sao_meta @form)
                     :help "numero alvo mensal"
                     :error (:sao_meta errors)
                     :on-change #(swap! form assoc :sao_meta %)}]
             [field {:label "SAO realizado"
                     :value (:sao_realizado @form)
                     :help "numero realizado no mes"
                     :error (:sao_realizado errors)
                     :on-change #(swap! form assoc :sao_realizado %)}]]
            [:div.form-grid.-tight
             [computed-field {:label "Meta de vidas"
                              :value (when (pos? (or vidas-meta 0))
                                       (fmt-int vidas-meta))
                              :help (case (:porte effective-form)
                                      "M" "calculada como Meta SAO x 375"
                                      "G+" "calculada como Meta SAO x 2000"
                                      "cadastre o porte do CN")
                              :error (:vidas_meta errors)}]
             [field {:label "Vidas realizadas"
                     :value (:vidas_realizado @form)
                     :help "limitado a 150% na regra"
                     :error (:vidas_realizado errors)
                     :on-change #(swap! form assoc :vidas_realizado %)}]]
            [:div.sim-rule
             [:div.sim-rule-row
              [:span "score"]
              [:strong "70% SAO + 30% vidas"]]
             [:div.sim-rule-row
             [:span "vidas"]
              [:strong (case (:porte effective-form)
                         "M" "meta = SAO x 375"
                         "G+" "meta = SAO x 2000"
                         "teto de 150%")]]
             [:div.sim-rule-row
              [:span "pagamento"]
              [:strong "base mensal x multiplicador"]]]
            (when (seq errors)
              [:div.callout.sim-error
               [layout/icon "alert" {:width 18 :height 18}]
               [:div
                [:strong "Preencha os campos para ver a simulacao"]
                [:p "A previa atualiza automaticamente assim que os dados obrigatorios ficam validos."]]])]]

          [score-card {:preview preview
                       :confirmed nil
                       :simulating? false}]]

         [:div.card.cn-chart-card
          [:div.card-head
           [:div
            [:h3 "Curva de multiplicador"]
            [:div.card-sub "Score final para multiplicador aplicado na regra mensal"]]
           [:div.legend
            [:span.legend-dot {:style {:color "var(--cyan)"}}
             (str "voce (" (fmt-mult (:multiplicador chart-result)) ")")]]]
          [multiplier-curve chart-result]]]))))
