(ns app.views.revops.policies
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.views.revops.policy-edit-modal :as edit-modal]
            [app.auth.subs]))

(defn- fmt-brl-int [v]
  (when v
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (str "R$ " (.toLocaleString (js/Math.round n) "pt-BR"))))))

(defn- or-dash [v] (if (or (nil? v) (= v "")) "—" v))

(def benefit-labels
  {"SAUDE" "Saúde" "ODONTO" "Odonto" "VIDA" "Vida"})

(defn- status->badge [s]
  (case s
    "PROJECTED"  [:span.badge.badge-paid "Ativa"]
    "IN_PAYMENT" [:span.badge.badge-validating "Em validação"]
    "SETTLED"    [:span.badge.badge-paid "Ativa"]
    "CANCELLED"  [:span.badge.badge-locked "Suspensa"]
    [:span.badge.badge-paid "Ativa"]))

(defn policies-page []
  (let [filters (r/atom {:status "" :segment "" :ev_id "" :page 1 :search ""})
        modal-open? (r/atom false)
        selected (r/atom nil)
        open-edit (fn [row] (reset! selected row) (reset! modal-open? true))
        close-edit #(reset! modal-open? false)]
    (rf/dispatch [:revops/fetch-policies @filters])
    (rf/dispatch [:revops/fetch-users])
    (fn []
      (let [policies @(rf/subscribe [:revops/policies])
            meta     @(rf/subscribe [:revops/policies-meta])
            loading? @(rf/subscribe [:revops/policies-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            total    (or (:total meta) (count policies))
            actives  (count (filter #(= (:commission_status %) "PROJECTED") (or policies [])))
            in-validation (count (filter #(= (:commission_status %) "IN_PAYMENT") (or policies [])))
            suspended (count (filter #(= (:commission_status %) "CANCELLED") (or policies [])))
            fetch-fn (fn [] (rf/dispatch [:revops/fetch-policies @filters]))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "apólices"]
          :title "Apólices"
          :subtitle (str total " apólices · " (count (->> policies (map :partner_operator) (filter some?) distinct)) " operadoras")
          :header-actions
          [[:div.search
            [layout/icon "search" {:width 14 :height 14}]
            [:input {:placeholder "PIP-XXXX, CNPJ, cliente…"
                     :value (:search @filters)
                     :on-change (fn [e]
                                  (swap! filters assoc :search (.. e -target -value))
                                  (fetch-fn))}]]
           [:button.btn.btn-secondary
            [layout/icon "filter" {:width 14 :height 14}] "Filtros"]
           [:button.btn.btn-primary
            {:on-click #(do (reset! selected nil) (reset! modal-open? true))}
            [layout/icon "plus" {:width 14 :height 14}] "Nova apólice"]]}

         ;; Filter chips
         [:div.filter-row
          [:div {:class (str "chip" (when (= "" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "") (fetch-fn))}
           (str "Todas (" total ")")]
          [:div {:class (str "chip" (when (= "PROJECTED" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "PROJECTED") (fetch-fn))}
           (str "Ativas (" actives ")")]
          [:div {:class (str "chip" (when (= "CANCELLED" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "CANCELLED") (fetch-fn))}
           (str "Suspensas (" suspended ")")]
          [:div {:class (str "chip" (when (= "IN_PAYMENT" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "IN_PAYMENT") (fetch-fn))}
           (str "Em validação (" in-validation ")")]
          [:div {:style {:margin-left "auto" :font-family "var(--font-mono)" :font-size "11px"
                         :color "var(--fg-3)"}}
           "última sync: há 12 min"]]

         ;; Table
         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "Apólice"]
             [:th "Cliente"]
             [:th "Operadora"]
             [:th "EV"]
             [:th.center "Vidas"]
             [:th.right "MRR"]
             [:th "Vigência"]
             [:th "Status"]
             [:th.right ""]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 9 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? policies)
              [:tr [:td {:col-span 9 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma apólice encontrada"]]

              :else
              (for [p policies]
                ^{:key (or (:id p) (:numero_apolice p))}
                [:tr
                 [:td.name.num (or-dash (:numero_apolice p))]
                 [:td (or (:client_name p) "—")
                  (when (:client_cnpj p)
                    [:span.muted (str " · " (:client_cnpj p))])]
                 [:td.muted (or-dash (:partner_operator p))]
                 [:td (or-dash (:ev_name p))]
                 [:td.center.num (str (or (:lives p) "—"))]
                 [:td.right.strong-num (or (fmt-brl-int (:mrr_for_commission p)) "—")]
                 [:td.num.muted (or (:vigencia p) "—")]
                 [:td [status->badge (:commission_status p)]]
                 [:td.right
                  [:button.btn.btn-ghost.btn-sm
                   {:on-click #(open-edit p)}
                   [layout/icon "edit" {:width 12 :height 12}]]]]))]]
          [:div {:style {:padding "12px 20px" :border-top "1px solid var(--border-subtle)"
                         :display "flex" :justify-content "space-between"
                         :font-family "var(--font-mono)" :font-size "11px" :color "var(--fg-3)"}}
           [:span (str "1–" (count policies) " de " total)]
           [:div {:style {:display "flex" :gap "8px"}}
            [:button.btn.btn-secondary.btn-sm
             {:disabled (<= (or (:page meta) 1) 1)
              :on-click #(do (swap! filters update :page (fnil dec 1)) (fetch-fn))}
             "‹"]
            [:button.btn.btn-secondary.btn-sm
             {:disabled (>= (or (:page meta) 1) (or (:total_pages meta) 1))
              :on-click #(do (swap! filters update :page (fnil inc 1)) (fetch-fn))}
             "›"]]]]

         [edit-modal/policy-edit-modal
          {:open? @modal-open?
           :policy @selected
           :on-close close-edit}]]))))
