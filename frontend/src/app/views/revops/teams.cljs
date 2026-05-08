(ns app.views.revops.teams
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

(defn- empty-team-form [] {:name "" :leader_id ""})

(defn- team-form-from [team-data]
  (merge (empty-team-form)
         (select-keys (or team-data {}) [:name :leader_id])
         (when (:leader_id team-data) {:leader_id (str (:leader_id team-data))})))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- stat-col [{:keys [label value color]}]
  [:div
   [:div {:style {:font-family "var(--font-mono)" :font-size "10.5px"
                  :color "var(--fg-3)" :text-transform "uppercase"
                  :letter-spacing "0.06em"}}
    label]
   [:div {:style {:font-family "var(--font-display)" :font-size "22px"
                  :color (or color "var(--fg-1)")}}
    value]])

(defn team-modal []
  (let [form (r/atom (empty-team-form))]
    (r/create-class
      {:component-did-mount
       (fn [this]
         (reset! form (team-form-from (-> this .-props .-argv second :team-data))))
       :reagent-render
       (fn [{:keys [open? on-close team-data users]}]
         (let [editing? (some? (:id team-data))
               leader-options (into [{:value "" :label "Sem líder"}]
                                    (map #(hash-map :value (str (:id %)) :label (:name %))
                                         (filter #(= (:role %) "LIDER_VENDAS") (or users []))))]
           [modal/modal {:open? open? :on-close on-close
                         :title (if editing? "Editar Time" "Novo Time") :size :sm}
            [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
             [inputs/input {:label "Nome do Time" :value (:name @form) :required true
                            :on-change #(swap! form assoc :name %)}]
             [inputs/select {:label "Líder de Vendas"
                             :value (or (:leader_id @form) "")
                             :options leader-options
                             :on-change #(swap! form assoc :leader_id %)}]
             [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
              [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
              [btn/button {:variant :primary
                           :disabled (str/blank? (:name @form))
                           :on-click (fn []
                                       (let [payload (-> @form
                                                         (update :leader_id #(when-not (str/blank? %) %)))]
                                         (if editing?
                                           (rf/dispatch [:revops/update-team (:id team-data) payload])
                                           (rf/dispatch [:revops/create-team payload])))
                                       (on-close))}
               (if editing? "Salvar" "Criar")]]]]))})))

(defn teams-page []
  (rf/dispatch [:revops/fetch-teams])
  (rf/dispatch [:revops/fetch-users])
  (let [modal-open?  (r/atom false)
        editing-team (r/atom nil)
        confirm-open?(r/atom false)
        confirm-row  (r/atom nil)]
    (fn []
      (let [teams @(rf/subscribe [:revops/teams])
            users @(rf/subscribe [:revops/users])
            loading? @(rf/subscribe [:revops/teams-loading?])
            user  @(rf/subscribe [:auth/current-user])
            route @(rf/subscribe [:current-route-name])
            team-rows (or teams [])
            total-evs (reduce + 0 (map #(count (:members %)) team-rows))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "times"]
          :title "Times"
          :subtitle (str (count team-rows) " times · " total-evs " vendedores ativos")
          :header-actions
          [[:button.btn.btn-primary
            {:on-click #(do (reset! editing-team nil) (reset! modal-open? true))}
            [layout/icon "plus" {:width 14 :height 14}] "Novo time"]]}

         (cond
           loading?
           [:div.card [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                       "Carregando…"]]

           (empty? team-rows)
           [:div.card
            [:div.empty
             [:div.empty-illus [layout/icon "team" {:width 40 :height 40}]]
             [:h4 "Nenhum time configurado"]
             [:p "Crie o primeiro time para organizar seus EVs."]
             [:button.btn.btn-primary.btn-sm
              {:style {:margin-top "8px"}
               :on-click #(do (reset! editing-team nil) (reset! modal-open? true))}
              "Novo time"]]]

           :else
           [:div.form-grid.-three
            (for [t team-rows]
              ^{:key (:id t)}
              [:div.card
               [:div.card-head
                [:div [:h3 (:name t)]
                 [:div.card-sub (str "líder: " (or (:leader_name t) "·"))]]
                [:button.btn.btn-ghost.btn-sm
                 {:on-click #(do (reset! editing-team t) (reset! modal-open? true))
                  :title "Editar time"}
                 [layout/icon "edit" {:width 12 :height 12}]]]
               [:div {:style {:display "flex" :gap "14px" :margin-top "4px" :flex-wrap "wrap"}}
                [stat-col {:label "composição"
                           :value (str (count (:members t)) " EVs")}]
                (when-let [mrr (:mrr_sum t)]
                  [stat-col {:label "MRR" :value (str "R$ " (fmt-int mrr))}])
                (when-let [pct (:achievement_pct t)]
                  [stat-col {:label "atingim."
                             :value (str pct "%")
                             :color (cond
                                      (>= pct 100) "var(--success-dark)"
                                      (>= pct 70)  "var(--warning-dark)"
                                      :else        "var(--danger-dark)")}])]])])

         ^{:key (str "team-modal-" (or (:id @editing-team) "new") "-" @modal-open?)}
         [team-modal {:open? @modal-open? :on-close #(reset! modal-open? false)
                      :team-data @editing-team :users users}]

         [modal/confirm-dialog
          {:open? @confirm-open?
           :on-close #(reset! confirm-open? false)
           :on-confirm (fn []
                         (when-let [row @confirm-row]
                           (rf/dispatch [:revops/delete-team (:id row)]))
                         (reset! confirm-open? false))
           :title "Confirmar remoção"
           :message (str "Remover " (:name @confirm-row) "?")
           :confirm-label "Remover"
           :variant :danger}]]))))
