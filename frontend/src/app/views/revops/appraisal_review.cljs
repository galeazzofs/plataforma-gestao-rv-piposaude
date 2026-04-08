(ns app.views.revops.appraisal-review
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (str "R$ " (.toLocaleString n "pt-BR"
                                    #js {:minimumFractionDigits 2
                                         :maximumFractionDigits 2}))))))

(defn fmt-pct [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (str (.toFixed n 1) "%")))))

;; ── NF list inside a Policy ───────────────────────────────

(defn nf-list-table [nfs]
  [tbl/data-table
   {:columns
    [{:key :data_recebimento :label "Data" :width "110px"}
     {:key :tipo_receita :label "Tipo" :width "150px"}
     {:key :nf_liquido :label "NF Líquido" :align "right"
      :render (fn [r] (fmt-brl (:nf_liquido r)))}]
    :rows nfs
    :empty-message "—"}])

;; ── Policy block (one per Policy under an EV) ─────────────

(defn policy-block [policy]
  (let [open? (r/atom false)]
    (fn [policy]
      [:div {:style {:border (str "1px solid " t/border-default)
                     :border-radius (:md t/border-radius)
                     :padding "12px" :margin-bottom "8px"
                     :background t/bg-card}}
       [:div {:style {:display "flex" :justify-content "space-between"
                      :align-items "center" :cursor "pointer"}
              :on-click #(swap! open? not)}
        [:div
         [:strong (or (:client_name policy) "—")]
         [:span {:style {:color t/text-secondary :margin-left "8px"
                         :font-size (:sm t/font-sizes)}}
          (str (or (:operadora policy) "—") " · "
               (or (:produto policy) "—") " · "
               (or (:segment policy) "—"))]]
        [:div {:style {:font-weight (:semibold t/font-weights)}}
         (fmt-brl (:subtotal policy))]]
       (when @open?
         [:div {:style {:margin-top "12px" :padding-top "12px"
                        :border-top (str "1px solid " t/border-default)}}
          [:div {:style {:display "flex" :gap "16px" :margin-bottom "8px"
                         :flex-wrap "wrap"
                         :font-size (:sm t/font-sizes) :color t/text-secondary}}
           [:div "Início vigência: " (or (:first_payment_real policy) "—")]
           [:div "Gongo: " (or (:closed_date policy) "—")]
           [:div "Atingimento usado: " (fmt-pct (:achievement_used_pct policy))]
           [:div "% Comissão: " (fmt-pct (* 100 (or (:commission_pct policy) 0)))]]
          [nf-list-table (:nfs policy)]])])))

;; ── EV row ────────────────────────────────────────────────

(defn ev-row []
  (let [open? (r/atom false)]
    (fn [ev tipo-filter operadora-filter]
      (let [filter-nfs (fn [nfs]
                         (if (or (nil? tipo-filter) (= "Todos" tipo-filter))
                           nfs
                           (filter #(= (:tipo_receita %) tipo-filter) nfs)))
            filtered (->> (:policies ev)
                          (filter (fn [p]
                                    (or (nil? operadora-filter)
                                        (= "Todas" operadora-filter)
                                        (= (:operadora p) operadora-filter))))
                          (map (fn [p] (update p :nfs filter-nfs))))]
        [:div {:style {:border (str "1px solid " t/border-default)
                       :border-radius (:md t/border-radius)
                       :margin-bottom "12px"
                       :background t/bg-card}}
         [:div {:style {:padding "16px" :cursor "pointer"
                        :display "flex" :justify-content "space-between"
                        :align-items "center"}
                :on-click #(swap! open? not)}
          [:div
           [:div {:style {:font-weight (:semibold t/font-weights)
                          :font-size (:lg t/font-sizes)}} (:ev_name ev)]
           [:div {:style {:color t/text-secondary :font-size (:sm t/font-sizes)
                          :margin-top "4px"}}
            (str (:policies_count ev) " apólices · "
                 (:nf_count ev) " NFs · "
                 "Atingimento: " (or (fmt-pct (:achievement_pct ev)) "—"))]]
          [:div {:style {:font-size (:xl t/font-sizes)
                         :font-weight (:bold t/font-weights)
                         :color t/color-primary}}
           (fmt-brl (:total_commission ev))]]
         (when @open?
           [:div {:style {:padding "0 16px 16px 16px"}}
            (for [p filtered]
              ^{:key (:policy_id p)} [policy-block p])])]))))

;; ── Por EV tab ────────────────────────────────────────────

(defn por-ev-tab []
  (let [tipo-filter (r/atom "Todos")
        op-filter (r/atom "Todas")]
    (fn [ev-summary]
      (let [all-ops (->> ev-summary
                         (mapcat :policies)
                         (map :operadora)
                         (remove nil?)
                         distinct
                         sort)]
        [:div
         [:div {:style {:display "flex" :gap "12px" :margin-bottom "16px"
                        :align-items "flex-end"}}
          [:div {:style {:width "200px"}}
           [inputs/select
            {:label "Tipo Receita" :value @tipo-filter
             :options [{:value "Todos" :label "Todos"}
                       {:value "Comissão" :label "Comissão"}
                       {:value "Fee por Vida" :label "Fee por Vida"}
                       {:value "Premiação" :label "Premiação"}
                       {:value "Patrocínio - Eventos" :label "Patrocínio"}
                       {:value "Agenciamento" :label "Agenciamento"}]
             :on-change #(reset! tipo-filter %)}]]
          [:div {:style {:width "240px"}}
           [inputs/select
            {:label "Operadora" :value @op-filter
             :options (cons {:value "Todas" :label "Todas"}
                            (map (fn [o] {:value o :label o}) all-ops))
             :on-change #(reset! op-filter %)}]]]
         (if (empty? ev-summary)
           [:div {:style {:padding "48px" :text-align "center"
                          :color t/text-secondary}}
            "Nenhum EV com comissão calculada"]
           (for [ev ev-summary]
             ^{:key (:ev_id ev)} [ev-row ev @tipo-filter @op-filter]))]))))

;; ── Generic NF table for unmatched/expired/nao-suportado ──

(defn nf-table [rows]
  [tbl/data-table
   {:columns
    [{:key :cliente_mae :label "Cliente"}
     {:key :operadora :label "Operadora"}
     {:key :produto :label "Produto" :width "100px"}
     {:key :data_recebimento :label "Data" :width "110px"}
     {:key :tipo_receita :label "Tipo" :width "140px"}
     {:key :nf_liquido :label "NF Líquido" :align "right"
      :render #(fmt-brl (:nf_liquido %))}
     {:key :match_status :label "Status" :width "150px"
      :render #(do [badge/badge {:variant :warning} (:match_status %)])}]
    :rows rows
    :empty-message "Nenhuma linha"}])

(defn export-csv-button [rows filename]
  [btn/button
   {:variant :secondary :size :sm
    :on-click
    (fn []
      (let [headers ["cliente_mae" "operadora" "produto" "data_recebimento"
                     "tipo_receita" "nf_liquido" "match_status"]
            quote (fn [v] (str "\"" (or v "") "\""))
            line (fn [r] (str/join "," (map #(quote (get r (keyword %))) headers)))
            csv (str/join "\n" (cons (str/join "," headers) (map line rows)))
            blob (js/Blob. #js [csv] #js {:type "text/csv"})
            url (.createObjectURL js/URL blob)
            a (.createElement js/document "a")]
        (set! (.-href a) url)
        (set! (.-download a) filename)
        (.click a)
        (.revokeObjectURL js/URL url)))}
   "📥 Exportar CSV"])

;; ── Page ──────────────────────────────────────────────────

(defn appraisal-review-page []
  (let [route @(rf/subscribe [:current-route])
        appraisal-id (get-in route [:path-params :id])
        active-tab (r/atom :por-ev)]
    (when appraisal-id
      (rf/dispatch [:revops/fetch-appraisal-detail appraisal-id])
      (rf/dispatch [:revops/fetch-appraisals]))
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            appraisal (first (filter #(= (str (:id %)) (str appraisal-id))
                                     (or appraisals [])))
            ev-summary (or (:ev_summary appraisal) [])
            unmatched (or (:unmatched appraisal) [])
            expired (or (:expired appraisal) [])
            nao-sup (or (:nao_suportado appraisal) [])
            totals (or (:totals appraisal) {})
            user @(rf/subscribe [:auth/current-user])
            route-name @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route-name
          :user user
          :title "Revisão de Apuração"
          :subtitle (when appraisal (str "Q" (:quarter appraisal) "/" (:year appraisal)))
          :header-actions
          [:div {:style {:display "flex" :gap "8px"}}
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:navigate! :revops/appraisal])}
            "← Voltar"]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/recalculate-appraisal appraisal-id])}
            "🔄 Recalcular"]
           [btn/button {:variant :primary
                        :on-click #(rf/dispatch [:revops/release-to-validation appraisal-id])}
            "✅ Liberar para Validação EVs"]]}

         [cards/card {}
          [:div {:style {:display "flex" :gap "32px" :margin-bottom "20px"
                         :padding "16px" :background t/bg-main
                         :border-radius (:md t/border-radius)
                         :flex-wrap "wrap"}}
           [:div [:div {:style {:font-size (:xs t/font-sizes)
                                :color t/text-secondary
                                :text-transform "uppercase"}}
                  "Total"]
            [:div {:style {:font-size (:xl t/font-sizes)
                           :font-weight (:bold t/font-weights)
                           :color t/color-primary}}
             (or (fmt-brl (:total_commission totals)) "R$ 0,00")]]
           [:div [:div {:style {:font-size (:xs t/font-sizes)
                                :color t/text-secondary
                                :text-transform "uppercase"}} "EVs"]
            [:div {:style {:font-size (:lg t/font-sizes)
                           :font-weight (:semibold t/font-weights)}}
             (str (:ev_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes)
                                :color t/text-secondary
                                :text-transform "uppercase"}} "Apólices"]
            [:div {:style {:font-size (:lg t/font-sizes)
                           :font-weight (:semibold t/font-weights)}}
             (str (:policy_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes)
                                :color t/text-secondary
                                :text-transform "uppercase"}} "NFs OK"]
            [:div {:style {:font-size (:lg t/font-sizes)
                           :font-weight (:semibold t/font-weights)}}
             (str (:matched_nf_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes)
                                :color t/text-secondary
                                :text-transform "uppercase"}} "Não Match"]
            [:div {:style {:font-size (:lg t/font-sizes)
                           :font-weight (:semibold t/font-weights)
                           :color t/error-default}}
             (str (:unmatched_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes)
                                :color t/text-secondary
                                :text-transform "uppercase"}} "Fora Vig"]
            [:div {:style {:font-size (:lg t/font-sizes)
                           :font-weight (:semibold t/font-weights)
                           :color t/warning-default}}
             (str (:expired_count totals 0))]]]

          ;; Tabs
          [:div {:style {:display "flex" :gap "4px" :margin-bottom "16px"
                         :border-bottom (str "1px solid " t/border-default)}}
           (for [{:keys [k label]}
                 [{:k :por-ev    :label "Por EV"}
                  {:k :unmatched :label (str "Não matcheadas (" (count unmatched) ")")}
                  {:k :expired   :label (str "Fora de vigência (" (count expired) ")")}
                  {:k :nao-sup   :label (str "Não suportado (" (count nao-sup) ")")}]]
             ^{:key k}
             [:button {:on-click #(reset! active-tab k)
                       :style {:padding "12px 18px"
                               :background "none"
                               :border "none"
                               :border-bottom (str "2px solid "
                                                   (if (= @active-tab k)
                                                     t/color-primary "transparent"))
                               :color (if (= @active-tab k)
                                        t/color-primary t/text-secondary)
                               :font-weight (:semibold t/font-weights)
                               :cursor "pointer"}}
              label])]

          (case @active-tab
            :por-ev    [por-ev-tab ev-summary]
            :unmatched [:div
                        [:div {:style {:margin-bottom "12px"}}
                         [export-csv-button unmatched "nao-matcheadas.csv"]]
                        [nf-table unmatched]]
            :expired   [:div
                        [:div {:style {:margin-bottom "12px"}}
                         [export-csv-button expired "fora-vigencia.csv"]]
                        [nf-table expired]]
            :nao-sup   [:div
                        [:p {:style {:color t/text-secondary
                                     :font-size (:sm t/font-sizes)
                                     :margin-bottom "12px"}}
                         "Linhas com produto não suportado pelo modelo (Mental, Fitness)."]
                        [nf-table nao-sup]])]]))))
